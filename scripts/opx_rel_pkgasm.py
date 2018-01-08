#! /usr/bin/python
"""
opx_rel_pkgasm.py -- assemble release object from packages

    Assemble an OPX release from packages
"""

from __future__ import print_function

import argparse
import collections
import datetime
import errno
import fileinput
import glob
import hashlib
import jinja2
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import time

from lxml import etree
from lxml.builder import E

import opx_bld_basics
import opx_get_packages
import opx_rootfs

build_num = 99999
build_suffix = ""
verbosity = 0

RELEASE_MAPPING = {
    'oldstable': '2.0',
    'stable': '2.1',
    'testing': '2.2',
    'unstable': '2.2-dev',
}

DISTRIBUTIONS = [
    'oldstable',
    'stable',
    'testing',
    'unstable',
    '2.0',
    '2.1',
    '2.2',
]


def _str2bool(s):
    """
    Convert string to boolean

    Used by XML serialization
    """

    s = s.strip().lower()
    if s in ["1", "true"]:
        return True
    if s in ["0", "false"]:
        return False

    raise ValueError("Invalid boolean value %r" % (s))


def _bool2str(b):
    """
    Convert boolean to string

    Used by XML serialization
    """

    return "true" if b else "false"


def art8601_format(dt):
    """
    Format datetime object in ISO 8601 format suitable for Artifactory.

    Artifactory's ISO 8601 timestamp parser is strict. It only accepts
    3 sigificant digits of sub-second precision (milliseconds) instead
    of the 6 significant digits (microseconds) in datetime.isoformat()
    output.

    I've raised a support ticket asking JFrog to consider relaxing
    their parser.

    Code adapted from standard python library.
    """

    s = '%04d-%02d-%02dT%02d:%02d:%02d.%03d' % (
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second,
        dt.microsecond / 1000)

    utc_offset = dt.utcoffset()
    if utc_offset is not None:
        if utc_offset.days < 0:
            sign = '-'
            utc_offset = - utc_offset
        else:
            sign = '+'

        hh, mm = divmod(utc_offset.seconds, 3600)
        mm //= 60

        s += "%s%02d%02d" % (sign, hh, mm)
    else:
        s += "Z"

    return s


class OpxRelPackageRestriction(object):
    """
    Represents a package version restriction.

    Loosely based on Maven's Restriction object API.
    """
    def __init__(self, lower_bound,
                 lower_bound_inclusive,
                 upper_bound,
                 upper_bound_inclusive):
        self.lower_bound = lower_bound
        self.lower_bound_inclusive = lower_bound_inclusive
        self.upper_bound = upper_bound
        self.upper_bound_inclusive = upper_bound_inclusive

    def toDebian(self):
        """
        Return list of version restrictions in Debian format
        :returns: list of version specifications
        """
        # special case equality
        if (self.lower_bound_inclusive and
                self.lower_bound == self.upper_bound and
                self.upper_bound_inclusive):
            return ['=' + self.lower_bound]

        # special case inequality
        if (not self.lower_bound_inclusive and
                self.lower_bound == self.upper_bound and
                not self.upper_bound_inclusive):
            return ['!=' + self.lower_bound]

        restrictions = list()
        if self.lower_bound is not None:
            if self.lower_bound_inclusive:
                restrictions.append('>=' + self.lower_bound)
            else:
                restrictions.append('>>' + self.lower_bound)
        if self.upper_bound is not None:
            if self.upper_bound_inclusive:
                restrictions.append('<=' + self.upper_bound)
            else:
                restrictions.append('<<' + self.upper_bound)

        return restrictions

    def __str__(self):
        """
        Override str method for a pretty format of the data members.
        """
        # special case equality
        if (self.lower_bound_inclusive and
                self.lower_bound == self.upper_bound and
                self.upper_bound_inclusive):
            return '[' + self.lower_bound + ']'

        # special case inequality
        if (not self.lower_bound_inclusive and
                self.lower_bound == self.upper_bound and
                not self.upper_bound_inclusive):
            return '(' + self.lower_bound + ')'

        s = '[' if self.lower_bound_inclusive else '('
        if self.lower_bound is not None:
            s += self.lower_bound
        s += ','
        if self.upper_bound is not None:
            s += self.upper_bound
        s += ']' if self.upper_bound_inclusive else ')'

        return s


class OpxRelPackage(object):
    """
    Defines a package in a :class:`OpxRelPackageSet`.
    """

    def __init__(self, name, restriction):
        self.name = name
        self.restriction = restriction

    @classmethod
    def fromElement(cls, elem):
        """
        Construct :class:`OpxRelPackage` object from :class:`etree.Element`
        """

        # Legacy blueprints define the package name and revision
        # specification in the text field of the package element.
        # Current blueprints use name and version attributes.
        #
        # .. note::
        #    There was some debate whether name and version should
        #    be attributes or elements in their own right. We used
        #    attributes for now, but if it turns out we made the
        #    wrong choice, it's easy enough to change.

        if elem.text:
            match = re.match(r'\A([a-zA-Z0-9][a-zA-Z0-9+-.]+)\s*(?:\(\s*(<<|<=|!=|=|>=|>>)\s*([0-9][a-z0-9+-.:~]+)\s*\))?\s*\Z', elem.text)
            if not match:
                raise ValueError("Can't parse version: ->%s<-" % elem.text)

            name = match.group(1)
            relation = match.group(2)
            version = match.group(3)

            restriction = None

            if relation:
                if relation == '<<':
                    lower_bound = None
                    lower_bound_inclusive = False
                    upper_bound = version
                    upper_bound_inclusive = False
                elif relation == '<=':
                    lower_bound = None
                    lower_bound_inclusive = False
                    upper_bound = version
                    upper_bound_inclusive = True
                elif relation == '!=':
                    lower_bound = version
                    lower_bound_inclusive = False
                    upper_bound = version
                    lower_bound_inclusive = False
                elif relation == '=':
                    lower_bound = version
                    lower_bound_inclusive = True
                    upper_bound = version
                    lower_bound_inclusive = True
                elif relation == '>=':
                    lower_bound = version
                    lower_bound_inclusive = True
                    upper_bound = None
                    upper_bound_inclusive = False
                elif relation == '>>':
                    lower_bound = version
                    lower_bound_inclusive = True
                    upper_bound = None
                    upper_bound_inclusive = False

                restriction = OpxRelPackageRestriction(
                    lower_bound,
                    lower_bound_inclusive,
                    upper_bound,
                    upper_bound_inclusive)

            return OpxRelPackage(name, restriction)

        name = elem.get('name')
        version = elem.get('version')
        if not version:
            return OpxRelPackage(name, None)

        match = re.match(r'\A([[(])([0-9][a-z0-9+-.:~]+)?,([0-9][a-z0-9+-.:~]+)?([])])\Z', version)
        if match:
            restriction = OpxRelPackageRestriction(
                match.group(2),
                match.group(1) == '[',
                match.group(3),
                match.group(4) == ']')
            return OpxRelPackage(name, restriction)

        # special case equality
        match = re.match(r'\A\[([0-9][a-z0-9+-.:~]+)\]\Z', version)
        if match:
            restriction = OpxRelPackageRestriction(
                match.group(1),
                True,
                match.group(1),
                True)
            return OpxRelPackage(name, restriction)

        # special case inequality
        match = re.match(r'\A\(([0-9][a-z0-9+-.:~]+)\)\Z', version)
        if match:
            restriction = OpxRelPackageRestriction(
                match.group(1),
                False,
                match.group(1),
                False)
            return OpxRelPackage(name, restriction)

        raise ValueError("Can't parse version: ->%s<-" % version)

    def toElement(self):
        """
        Return :class:`etree.Element` representing :class:`OpxRelPackage`
        :returns: :class:`etree.Element`
        """

        attributes = collections.OrderedDict()
        attributes['name'] = self.name
        if self.restriction:
            attributes['version'] = str(self.restriction)

        return E.package(attributes)

    def toDebian(self):
        """
        Return list of package name+version restrictions in Debian format
        :returns: list of version specifications for this package
        """
        if self.restriction is not None:
            return ["{}({})".format(self.name, x)
                    for x in self.restriction.toDebian()]
        else:
            return [self.name]

    def __str__(self):
        """
        Override str method for a pretty format of the data members.
        """
        s = self.name
        if self.restriction is not None:
            s += " "
            s += str(self.restriction)
        return s


class OpxRelPackageList(object):
    """
    Defines a list of packages, each one being an :class:`OpxRelPackage`
    """
    def __init__(self, package_list, no_package_filter=False):
        self.packages = package_list
        self.no_package_filter = no_package_filter

    @classmethod
    def fromElement(cls, element):
        """
        Construct :class:`OpxRelPackageList` object from :class:`etree.Element`
        """
        # no_package_filter is local as this is a classmethod
        if element.find('no_package_filter') is not None:
            no_package_filter = True
        else:
            no_package_filter = False

        package_list = []
        for package_elem in element.findall('package'):
            package_list.append(OpxRelPackage.fromElement(package_elem))

        return OpxRelPackageList(package_list, no_package_filter)

    def toElement(self):
        """
        Return :class:`etree.Element` representing :class:`OpxRelPackageList`
        :returns: :class:`etree.Element`
        """
        elem = E.package_list()

        if self.no_package_filter:
            elem.append(E.no_package_filter())

        for package in self.packages:
            elem.append(package.toElement())

        return elem


class OpxRelPackageSet(object):
    """
    Defines a package set, including a list of packages,
     and where to find/get them.
    """
    def __init__(self, name, kind, default_solver, platform, flavor,
                    package_sources, package_lists):
        self.name = name
        self.kind = kind
        self.default_solver = default_solver
        self.platform = platform
        self.flavor = flavor
        self.package_sources = package_sources
        self.package_lists = package_lists

    @classmethod
    def fromElement(cls, elem):
        """
        Construct :class:`OpxRelPackageSet` object from :class:`etree.Element`
        """

        name = elem.find('name').text
        kind = elem.find('type').text

        if elem.find('default_solver') is not None:
            default_solver = True
        else:
            default_solver = False

        _tmp = elem.find('platform')
        if _tmp is not None:
            platform = _tmp.text
        else:
            platform = None

        _tmp = elem.find('flavor')
        if _tmp is not None:
            flavor = _tmp.text
        else:
            flavor = None

        package_sources = []
        for package_desc_elem in elem.findall('package_desc'):
            package_sources.append(
                opx_get_packages.OpxPackageSource(
                    package_desc_elem.find('url').text,
                    package_desc_elem.find('distribution').text,
                    package_desc_elem.find('component').text,
                )
            )

        package_lists = []
        for package_list_elem in elem.findall('package_list'):
            package_lists.append(OpxRelPackageList.fromElement(
                                                        package_list_elem))

        return OpxRelPackageSet(name, kind, default_solver, platform,
                                flavor, package_sources, package_lists)

    def toElement(self):
        """
        Return :class:`etree.Element` representing :class:`OpxRelPackageSet`
        :returns: :class:`etree.Element`
        """

        elem = E.package_set(
            E.name(self.name),
            E.type(self.kind)
        )

        if self.default_solver:
            elem.append(E.default_solver())

        if self.platform is not None:
            elem.append(E.platform(self.platform))

        if self.flavor is not None:
            elem.append(E.flavor(self.flavor))

        for package_source in self.package_sources:
            elem.append(
                E.package_desc(
                    E.url(package_source.url),
                    E.distribution(package_source.distribution),
                    E.component(package_source.component),
                )
            )

        elem.extend([package_list.toElement()
                        for package_list in self.package_lists])

        return elem

    def __str__(self):
        """
        Override str method for a pretty format of the Data members

        """
        mstr = "\n" + self.__class__.__name__
        mstr += " is an OpxRelPackageSet() instance\n"
        mstr += "\t" + self.name + "\n"
        mstr += "\twhich is a " + self.kind + "\n"
        mstr += "\tsources:\n"
        for src in self.package_sources:
            mstr += "\t\t%s [%s,%s]\n" % (
                src.url,
                src.distribution,
                src.component
            )
        mstr += "\tpackages:\n"
        for pkg_list in self.package_lists:
            for pkg in pkg_list.packages:
                mstr += "\t\t" + str(pkg) + "\n"
            mstr += "\n"

        return mstr


class OpxRelInstHook(object):
    """
    Installation hook file in an OPX release
    """
    def __init__(self, hook_file):
        hook_file_path = os.path.join('opx-onie-installer', 'inst-hooks',
                                      hook_file)
        if not os.path.exists(hook_file_path):
            print("Hook file %s does not exist" % hook_file_path,
                  file=sys.stderr)
            sys.exit(1)

        if not os.access(hook_file_path, os.X_OK):
            print("Hook file %s is not executable" % hook_file_path,
                  file=sys.stderr)
            sys.exit(1)

        self.hook_file = hook_file
        self.hook_file_path = hook_file_path

    @classmethod
    def fromElement(cls, elem):
        """
        Construct :class:`OpxRelInstHook` from :class:`etree.Element`
        """
        hook_file = elem.text
        return OpxRelInstHook(hook_file)

    def toElement(self):
        """
        Return :class:`etree.Element` representing :class:`OpxRelInstHook`
        :returns: :class:`etree.Element`
        """
        return E.inst_hook(self.hook_file)


class OpxRelBlueprint(object):
    """
    Blue Print to create an OPX release
    """
    def __init__(self, description, package_type,
                 platform, architecture, installer_suffix, version,
                 rootfs, output_format, package_sets, inst_hooks):

        self.description = description
        self.package_type = package_type
        self.platform = platform
        self.architecture = architecture
        self.installer_suffix = installer_suffix
        self.version = version
        self.rootfs = rootfs
        self.output_format = output_format
        self.package_sets = package_sets
        self.inst_hooks = inst_hooks
        self.validate()

    def validate(self):
        """
        Validate OpxRelBlueprint object

        Currently prints error and exits on invalid object.  Should probably
        throw an exception
        """
        # Insure that only one of the ONIE outputs is selected as they
        # are mutually exclusive ...
        if self.output_format['ONIE_pkg'] and self.output_format['ONIE_image']:
            print("ONIE pkg and image mutually exclusve - both true",
                  file=sys.stderr)
            sys.exit(1)

    @classmethod
    def fromElement(cls, elem, dist):
        """
        Construct :class:`OpxRelBlueprint` object from :class:`etree.Element`
        """

        description = elem.find('description').text
        package_type = elem.find('package_type').text
        platform = elem.find('platform').text
        architecture = elem.find('architecture').text
        installer_suffix = elem.find('installer_suffix').text
        version = elem.find('version').text

        rootfs_elem = elem.find('rootfs')
        rootfs = {
            'tar_name': rootfs_elem.find('tar_name').text,
            'source': rootfs_elem.find('source').text,
            'location': rootfs_elem.find('location').text,
            'url': os.path.join(rootfs_elem.find('source').text,
                                rootfs_elem.find('tar_name').text),
        }

        rootfs_md5_elem = rootfs_elem.find('md5')
        if rootfs_md5_elem is not None:
            rootfs['md5'] = rootfs_md5_elem.text
        else:
            rootfs['md5'] = None

        rootfs_sha1_elem = rootfs_elem.find('sha1')
        if rootfs_sha1_elem is not None:
            rootfs['sha1'] = rootfs_sha1_elem.text
        else:
            rootfs['sha1'] = None

        output_elem = elem.find('output_format')
        output_format = {
            'name': output_elem.find('name').text,
            'version': output_elem.find('version').text,
            'tar_archive': _str2bool(output_elem.find('tar_archive').text),
            'ONIE_image': _str2bool(output_elem.find('ONIE_image').text),
            'ONIE_pkg': _str2bool(output_elem.find('ONIE_pkg').text),
            'package_cache': _str2bool(output_elem.find('package_cache').text),
        }

        if dist in RELEASE_MAPPING:
            output_format['version'] = RELEASE_MAPPING[dist]
        else:
            output_format['version'] = dist

        package_sets = []
        for package_set_elem in elem.findall('package_set'):
            package_sets.append(OpxRelPackageSet.fromElement(package_set_elem))

        for p in package_sets:
            for s in p.package_sources:
                if 'copy:/mnt' in s.url or 'opx-apt' in s.url:
                    s.distribution = dist

        inst_hooks = []
        for hook_elem in elem.findall('inst_hook'):
            inst_hooks.append(OpxRelInstHook.fromElement(hook_elem))

        return OpxRelBlueprint(description, package_type,
                              platform, architecture, installer_suffix, version,
                              rootfs, output_format, package_sets,
                              inst_hooks)

    def toElement(self):
        """
        Return :class:`etree.Element` representing :class:`OpxRelBlueprint`
        :returns: :class:`etree.Element`
        """

        elem = E.blueprint(
            E.description(self.description),
            E.package_type(self.package_type),
            E.platform(self.platform),
            E.architecture(self.architecture),
            E.installer_suffix(self.installer_suffix),
            E.version(self.version),
            E.rootfs(
                E.tar_name(self.rootfs['tar_name']),
                E.source(self.rootfs['source']),
                E.location(self.rootfs['location'])
            ),
            E.output_format(
                E.name(self.output_format['name']),
                E.version(self.output_format['version']),
                E.tar_archive(_bool2str(self.output_format['tar_archive'])),
                E.ONIE_image(_bool2str(self.output_format['ONIE_image'])),
                E.ONIE_pkg(_bool2str(self.output_format['ONIE_pkg'])),
                E.package_cache(_bool2str(self.output_format['package_cache']))
            ),
            *[s.toElement() for s in self.package_sets]
        )

        elem.extend([s.toElement() for s in self.inst_hooks])

        return elem

    @classmethod
    def load_xml(cls, fd_, dist):
        tree = etree.parse(fd_)
        tree.xinclude()
        root = tree.getroot()
        return OpxRelBlueprint.fromElement(root, dist)

    def dumps_xml(self):
        root = etree.Element('blueprint',
                             nsmap={'xi': 'http://www.w3.org/2001/XInclude'})
        root.extend(self.toElement())

        return etree.tostring(root, xml_declaration=True, pretty_print=True)

    def dump_xml(self, fd_):
        root = etree.Element('blueprint',
                             nsmap={'xi': 'http://www.w3.org/2001/XInclude'})
        root.extend(self.toElement())

        tree = etree.ElementTree(root)
        tree.write(fd_, xml_declaration=True, pretty_print=True)

    # consider adding iterator class extensions so we can iterate
    #  through a set to get a coherent set of releases, that is
    #  create a set of release plans that can be executed in order
    #  with a single set of blue-prints
    def __str__(self):
        """
        Override the str method, to get it formatted,
         possibly to dump information into a formal log
        """
        mstr = self.__class__.__name__
        mstr += " is a OpxRelBluePrint()\n"
        mstr += self.description + "\n"
        mstr += "a collection of " + self.package_type + " packages\n"
        mstr += "Version:" + self.version + "\n"

        mstr += "root file system descriptor:\n"
        mstr += "\turl = %s\n" % (self.rootfs['url'])
        if self.rootfs['md5']:
            mstr += "\tmd5 = %s\n" % (self.rootfs['md5'])
        if self.rootfs['sha1']:
            mstr += "\tsha1 = %s\n" % (self.rootfs['sha1'])
        mstr += "\tlocation = %s\n" % (self.rootfs['location'])

        # print in order of creation by make_output
        name = "%s-%s.%s%s" % (self.output_format['name'],
                               self.output_format['version'],
                               str(build_num),
                               build_suffix
                               )

        mstr += "creates:\n"
        if self.output_format['package_cache']:
            mstr += "\t" + name + "-<specific name>-pkg_cache.tgz\n"
        if self.output_format['ONIE_image'] or self.output_format['ONIE_pkg']:
            mstr += "\t" + name + "-installer-<specific name>.bin\n"
        if self.output_format['tar_archive']:
            mstr += "\t" + name + "-<specific name>-rootfs.tgz\n"

        for p in self.package_sets:
            mstr += p.__str__()

        return mstr


class OpxRelPackageAssembler(object):
    """
    Create images as directed by blueprint
    """

    def __init__(self, blueprint):
        self._blueprint = blueprint
        self.artifacts = []
        self.dependencies = []

        # .. todo:: Need to assert current directory is ${PROJROOT} and
        # the opx-onie-installer repository is present

        # Create rootfs object
        #
        # .. todo:: Need to add a SHA or MD5 entry to the blueprint,
        # so we can validate the integrity of the rootfs tar archive.

        self._root_obj = opx_rootfs.Opxrootfs(
            rootfs_path=None,
            rootfs_url=self._blueprint.rootfs['url'],
            rootfs_md5=self._blueprint.rootfs['md5'],
            rootfs_sha1=self._blueprint.rootfs['sha1'])

        if verbosity >= 2:
            pathname = self._root_obj.rootpath('etc', 'passwd')
            try:
                with open(pathname, 'r') as pwd:
                    print("")
                    print("AFTER: %s:" % pathname)
                    for line in pwd.readlines():
                        print(line.strip())
                    print("")
            except:
                print("WARNING: AFTER, Can't read %s" % pathname)

    def get_version_info(self):
        """
        Determine the version based on Bamboo environment variables.
        """

        current_time = time.time()
        try:
            build_date = os.environ['bamboo_buildTimeStamp']
        except KeyError:
            build_date = time.strftime('%FT%T%z')

        current_localtime = time.localtime(current_time)
        current_year = current_localtime.tm_year
        copyright_string = "Copyright (c) 1999-%4d by Dell EMC Inc. All Rights Reserved."  \
                           % (current_year)

        version_info = {}
        version_info['name'] = self._blueprint.output_format['name']
        version_info['version'] = self._blueprint.output_format['version']
        version_info['build_num'] = build_num
        version_info['build_suffix'] = build_suffix
        version_info['platform'] = self._blueprint.platform
        version_info['architecture'] = self._blueprint.architecture
        version_info['bp_description'] = self._blueprint.description
        version_info['bp_version'] = self._blueprint.version
        version_info['build_date'] = build_date
        version_info['copyright'] = copyright_string

        return version_info

    def determine_version_info(self):
        """
        Determine the version based on Bamboo environment variables.
        """

        version_data = self.get_version_info()

        version_info = list()
        version_info.append('COPYRIGHT="%s"' % (version_data['copyright']))
        version_info.append('OS_NAME="Dell EMC Networking %s"'
                                                % (version_data['name']))
        version_info.append('OS_VERSION="%s"' % (version_data['version']))
        version_info.append('PLATFORM="%s"' % (version_data['platform']))
        version_info.append('ARCHITECTURE="%s"'
                            % (version_data['architecture']))
        version_info.append('INTERNAL_BUILD_ID="%s %s"'
                            % (version_data['bp_description'],
                                version_data['bp_version']))
        version_info.append('BUILD_VERSION="%s(%d)%s"' % (
                            version_data['version'],
                            version_data['build_num'],
                            version_data['build_suffix'],
                            )
                           )
        version_info.append('BUILD_DATE="%s"' % (version_data['build_date']))

        return version_info

    def set_installer_version_env(self, version_info):
        """
        Set environment variables used by onie-mk-opx.sh.
        """
        for line in version_info:
            (name, val) = re.split(r'=', line, maxsplit=1)
            os.environ['INSTALLER_%s' % (name)] = val
            sys.stderr.write("INFO: Set os.environ['INSTALLER_%s']=%s.\n"
                                                % (name, val))

    def write_etc_version_file(self, version_info):
        """
        Write /etc/OPX-release-version file.
        """

        ar_v_filename = self._root_obj.rootpath("etc", "OPX-release-version")
        try:
            with open(ar_v_filename, 'w') as ar_v_file:
                for line in version_info:
                    ar_v_file.write("%s\n" % (line))
                os.fchmod(ar_v_file.fileno(), 0644)
            subprocess.call(['/bin/ls', '-l', ar_v_filename])
        except IOError, msg:
            print("WARNING: Can't write '%s' : %s, in %s"
                    % (ar_v_filename, msg, os.getcwd()))

    def write_installer_file(self):
        """
        Write /root/install_opx.sh file.
        """
        print("write_installer_file(self)")

        opx_install_file = self._root_obj.rootpath("root", "install_opx.sh")

        # Create jinja2 environment, used for template expansion
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(
                        os.path.join(os.path.dirname(__file__), 'templates')))
        template = env.get_template('install_opx_sh')

        template_params = {}
        template_params['package_sets'] = []
        for pks in self._blueprint.package_sets:
            pks_params = {}
            pks_params['name'] = pks.name
            pks_params['platform'] = pks.platform
            pks_params['flavor'] = pks.flavor

            packages = []
            for pkg_list in pks.package_lists:
                for pkg in pkg_list.packages:
                    packages.append(pkg.name)

            pks_params['packages'] = packages

            template_params['package_sets'].append(pks_params)

        # Save version info into template
        template_params['release'] = self.get_version_info()

        try:
            with open(opx_install_file, 'w') as fd_:
                fd_.write(template.render(template_params))

            os.chmod(opx_install_file, stat.S_IRWXU | stat.S_IRWXG)

        except IOError, msg:
            print("WARNING: Can't write '%s' : %s, in %s"
                    % (opx_install_file, msg, os.getcwd()))

    def filter_packages(self):
        """
        filter_packages() check the list of packages against the installed
        packages in the rootfs, remove any that are already present
        """
        print("filter_packages(self)")

        rootfs_package_list = self._root_obj.installed_packages()

        for pks in self._blueprint.package_sets:
            for pkg_list in pks.package_lists:
                # Filter out packages that are already in rootfs
                pkg_list.packages = [package for package in pkg_list.packages
                    if pkg_list.no_package_filter
                        or package.name not in rootfs_package_list]

    def update_rootfs(self):
        """
        update_rootfs() updates the package list from the upstream
        and upgrades the packages to the latest available versions,
        in order to address upgrades/security patches issued since
        the rootfs was originally created.
        """
        print("update_rootfs(self)")

        script_nm = os.path.join(os.path.dirname(__file__),
                                 'templates', 'do_apt_upgrade_sh')
        self._root_obj.do_chroot(script_nm)


    def add_packages(self):
        """
        add_packages() add packages selected to the package cache
                iterates through the sets of packages
        """
        print("add_packages(self)")

        for pks in self._blueprint.package_sets:
            deb_package_list = []
            for pkg_list in pks.package_lists:
                for package in pkg_list.packages:
                    deb_package_list.extend(package.toDebian())

            if verbosity > 1:
                print('Load %s of %s' % (pks.name, pks.kind))

                for package_source in pks.package_sources:
                    print('from %s [%s,%s] %s' % (package_source.url,
                                               package_source.distribution,
                                               package_source.component,
                                               '(default solver)'
                                                if pks.default_solver else ''))

                print('Loading')
                print(deb_package_list)

            # fetch the packages from this package set
            with opx_get_packages.OpxPackages(
                                    sysroot=self._root_obj.rootpath(),
                                    pkg_sources=pks.package_sources,
                                    default_solver=pks.default_solver) \
                                as packer:
                packer.fetch(names=deb_package_list)

        # list all packages that have been fetched
        if verbosity > 2:
            for mfn in self._root_obj.listdir(
                    os.path.join("var", "cache", "apt", "archives")):
                print(mfn)

    def verify_packages(self):
        """
        verify_packages() checks that all the packages listed in the
            blueprint are present in the rootfs
        """
        print("verify_packages(self)")

        # Populate the package list with the packages from the blueprint
        deb_package_list = set()
        for pks in self._blueprint.package_sets:
            for pkg_list in pks.package_lists:
                for package in pkg_list.packages:
                    deb_package_list.add(package.name)

        if verbosity > 2:
            print("Expected package list: %s" % sorted(list(deb_package_list)))

        # Get the list of packages in the rootfs
        # This assumes that the packages are available in
        # /var/cache/apt/archives/
        packages_path = self._root_obj.rootpath('var', 'cache', 'apt',
                                            'archives')
        rootfs_package_list = set(os.path.basename(pkg).split('_')[0] for pkg in
            glob.glob(os.path.join(packages_path, '*.deb')))

        if verbosity > 2:
            print("Downloaded package list: %s"
                    % sorted(list(rootfs_package_list)))

        # Check if the rootfs_package_list is a superset of deb_package_list
        if not rootfs_package_list.issuperset(deb_package_list):
            print('Missing packages %s' %
                list(deb_package_list.difference(rootfs_package_list)))
            raise ValueError('Could not find all packages')

    def install_packages(self):
        """
        install_packages() -- install packages from package
                                cache created above
        """
        print("install_packages(self)")
        if verbosity > 1:
            print("Create the script")

        script_nm = os.path.join(os.path.dirname(__file__),
                                 'templates',
                                 'do_dpkg_sh')

        # We don't install packages if we are creating
        #  the ONIE installer with package cache payload
        if not self._blueprint.output_format['ONIE_pkg']:
            self._root_obj.do_chroot(script_nm)
        version_info = self.determine_version_info()
        self.write_etc_version_file(version_info)
        self.set_installer_version_env(version_info)

    def add_artifact(self, pathname):
        '''
        Record artifact for Artifactory build-info metadata
        '''
        with open(pathname, 'rb') as f:
            # Compute hashes
            h_md5 = hashlib.md5()
            h_sha1 = hashlib.sha1()
            buf = f.read(8192)
            while len(buf) > 0:
                h_md5.update(buf)
                h_sha1.update(buf)
                buf = f.read(8192)

        artifact = {
            'name': os.path.basename(pathname),
            'md5': h_md5.hexdigest(),
            'sha1': h_sha1.hexdigest(),
        }

        if pathname.endswith('.bin'):
            artifact['type'] = 'bin'
        elif pathname.endswith(('.tgz', '.tar.gz')):
            artifact['type'] = 'tgz'

        self.artifacts.append(artifact)

    def add_dependency(self, pathname):
        '''
        Record dependency for Artifactory build-info metadata
        '''

        h_md5 = self._root_obj.compute_md5(pathname)
        h_sha1 = self._root_obj.compute_sha1(pathname)

        dependency = {
            'id': os.path.basename(pathname),
            'md5': h_md5.hexdigest(),
            'sha1': h_sha1.hexdigest(),
        }

        if pathname.endswith('.deb'):
            dependency['type'] = 'deb'
        elif pathname.endswith(('.tgz', '.tar.gz')):
            dependency['type'] = 'tgz'

        self.dependencies.append(dependency)

    def copy_inst_hooks(self, dist):
        """
        copy_inst_hooks() -- copy the postinst hooks from
            the blueprint folder to the rootfs
        """
        print("copy_inst_hooks(self)")

        destpath = self._root_obj.rootpath('root', 'hooks')

        # Create the directory
        try:
            os.makedirs(destpath)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(destpath):
                pass
            else:
                raise

        for hook in self._blueprint.inst_hooks:
            shutil.copy(hook.hook_file_path, destpath)

            # Change distribution in apt inst-hook
            if hook.hook_file == '98-set-apt-sources.postinst.sh':
                new_hook = "{}/{}".format(destpath, hook.hook_file)
                subprocess.check_call([
                    "sed",
                    "-i",
                    "s/opx-apt unstable/opx-apt {}/g".format(dist),
                    new_hook,
                ])


    def make_output(self):
        """
        make_output() -- create requested output
            depends on the the plan, tests its request
            as True or False for package cache archive
            ONIE installer, or tar gzip archive of rootfs
        """

        print("make_output(self)")

        nm_prefix = "%s%s-%s.%s%s" % (
            "PKGS_" if self._blueprint.output_format['ONIE_pkg'] else "",
            self._blueprint.output_format['name'],
            self._blueprint.output_format['version'],
            str(build_num),
            build_suffix
            )

        nm_suffix = self._blueprint.installer_suffix

        pkgcache_path = "%s-%s-pkg_cache.tgz" % (nm_prefix, nm_suffix)

        rootfs_path = "%s-%s-rootfs.tgz" % (nm_prefix, nm_suffix)

        image_path = "%s-installer-%s.bin" % (nm_prefix, nm_suffix)

        # need to make a list of dir entries that endwith .deb
        path = os.path.join('var', 'cache', 'apt', 'archives')
        flist = [fnm for fnm in self._root_obj.listdir(path)
                    if fnm.endswith('.deb')]
        if verbosity > 2:
            print(flist)

        if flist:
            for f in flist:
                self.add_dependency(os.path.join(path, f))

            if self._blueprint.output_format['package_cache']:
                if verbosity > 1:
                    print("INFO: creating %s\n" % pkgcache_path)
                    sys.stdout.flush()

                try:
                    self._root_obj.tar_out(pkgcache_path,
                                            directory=path, files=flist)
                except opx_rootfs.OpxrootfsError as ex:
                    print("ERROR: package cache creation failed: %s" % (ex))
                    raise

                self.add_artifact(pkgcache_path)

        # clean out the debian package cache before we
        #  build the other (possibly) requested items
        if not self._blueprint.output_format['ONIE_pkg']:
            if verbosity > 1:
                print("INFO: removing files from the package cache")
                sys.stdout.flush()

            for debfn in flist:
                try:
                    self._root_obj.remove(os.path.join(path, debfn))
                except opx_rootfs.OpxrootfsError as ex:
                    print("WARNING: for Opxrootfs.remove(%s), ignoring %s."
                            % (path, ex))
        else:
            rootpath = self._root_obj.rootpath(path)
            opx_bld_basics.gen_package_list(rootpath)

            # add my ONIE installer package repository to sources.list
            #  over-writes the existing one, with the expectation that
            #  the installer can put the save version back in place
            fnm = self._root_obj.rootpath('etc', 'apt', 'sources.list.d',
                                            'installer.list')
            try:
                with open(fnm, 'w+') as fd_:
                    # Marker so it can be easily removed
                    fd_.write('#-ONIE REMOVE START\n')
                    fd_.write('# Added for special installer use\n')
                    fd_.write('deb file:/var/cache/apt/archives ./\n')
            except IOError as ex:
                print(ex)
                raise

            # Write the installer file
            self.write_installer_file()

        # Clean out apt state
        # -- rootfs should not not reference our package sources.
        for path in [
                os.path.join('etc', 'apt', 'sources.list'),
                os.path.join('etc', 'apt', 'sources.list.save'),
                os.path.join('var', 'cache', 'apt', 'pkgcache.bin'),
        ]:
            if self._root_obj.exists(path):
                if verbosity > 1:
                    print("INFO: removing %s" % path)
                    sys.stdout.flush()

                try:
                    self._root_obj.remove(path)
                except opx_rootfs.OpxrootfsError as ex:
                    print("WARNING: for Opxrootfs.remove(%s), ignoring %s."
                            % (path, ex))

        # Remove any artifacts left in the rootfs image /tmp directory
        for fnm in self._root_obj.listdir('/tmp'):
            path = os.path.join('/tmp', fnm)

            if verbosity > 1:
                print("INFO: removing %s" % path)
                sys.stdout.flush()

            if self._root_obj.isdir(path):
                try:
                    self._root_obj.rmtree(path)
                except opx_rootfs.OpxrootfsError as ex:
                    print("WARNING: for Opxrootfs.rmtree(%s), ignoring %s."
                            % (path, ex))
            else:
                try:
                    self._root_obj.remove(path)
                except opx_rootfs.OpxrootfsError as ex:
                    print("WARNING: for Opxrootfs.remove(%s), ignoring %s."
                            % (path, ex))

        # these output formats use a rootfs tar gzipped archive
        #  so build it here, package cache just pulls its contents
        #  out, but doesn't need to archive the root image
        if (self._blueprint.output_format['ONIE_image']
                or self._blueprint.output_format['ONIE_pkg']
                or self._blueprint.output_format['tar_archive']):
            if verbosity > 1:
                print("INFO: creating %s\n" % (rootfs_path))
                sys.stdout.flush()

            try:
                self._root_obj.tar_out(rootfs_path)
            except opx_rootfs.OpxrootfsError as ex:
                # Try to address the 'too many levels of symbolic links'
                # errors, which seem to happen randomly.
                print("WARNING: First attempt to create tar file failed: %s"
                        % (ex))
                try:
                    self._root_obj.tar_out(rootfs_path)
                except opx_rootfs.OpxrootfsError as ex:
                    print("ERROR: Second attempt to create tar file failed: %s"
                            % (ex))
                    raise

        # to create the ONIE image, we use the current sysroot
        #  archive to create the ONIE installer, create what
        #  would be the output of the open-source-rootfs build
        #  and use ngos.sh to build the ONIE installer image
        if (self._blueprint.output_format['ONIE_image']
                or self._blueprint.output_format['ONIE_pkg']):
            if verbosity > 1:
                print("creating %s\n" % (image_path))
                sys.stdout.flush()

            cmd = ['opx-onie-installer/onie/onie-mk-opx.sh',
                   self._blueprint.architecture,
                   image_path,
                   rootfs_path
            ]
            if verbosity > 2:
                print(cmd)

            try:
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as ex:
                print("ERROR: image creation failed: %s" % (ex))
                raise

            self.add_artifact(image_path)

        if self._blueprint.output_format['tar_archive']:
            self.add_artifact(rootfs_path)
        else:
            # If blueprint was not set to generate rootfs tarball,
            # should we remove it?
            pass


def index_local_packages(dist):
    """Run the idx-pkgs script from opx-build/scripts with the correct dist."""
    cmd = 'opx-build/scripts/idx-pkgs'
    try:
        subprocess.check_call([cmd, dist])
    except subprocess.CalledProcessError as ex:
        print("ERROR: indexing local packages failed: %s" % (ex))
        raise



def main():
    """
    command line method to assemble a release from packages
    """

    start_timestamp = datetime.datetime.now()

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug',
                        help=argparse.SUPPRESS,
                        action='store_true')
    parser.add_argument('-b', help="specify location of release blue-print",
                        required=True)
    parser.add_argument('-n', help="specify build number of release",
                        type=int, default=9999)
    parser.add_argument('-s', help="specify release number suffix",
                        type=str, default="")
    parser.add_argument('-v', help="specify verbosity level",
                        type=int, default=0)
    parser.add_argument('--build-info',
                        help="specify location of build-info json output")
    parser.add_argument('--build-url')
    parser.add_argument('--vcs-url')
    parser.add_argument('--vcs-revision')
    parser.add_argument(
        '-d', '--dist',
        help="Distribution to build",
        choices=DISTRIBUTIONS,
        default='unstable'
    )


    args = parser.parse_args()

    if args.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.WARNING

    logging.basicConfig(level=loglevel)

    # set the verboseness of the instance based on
    #  either the default or command line input
    #  could also give meaning to numeric levels here ...
    global verbosity
    verbosity = args.v

    global build_num, build_suffix
    build_num = args.n
    build_suffix = args.s if args.s == "" else ("-" + args.s)

    with open(args.b, 'r') as fd_:
        rel_blueprint = OpxRelBlueprint.load_xml(fd_, args.dist)

    if verbosity > 0:
        print(rel_blueprint)

    rel_plan = OpxRelPackageAssembler(rel_blueprint)
    rel_plan.update_rootfs()
    rel_plan.filter_packages()
    index_local_packages(args.dist)
    rel_plan.add_packages()
    rel_plan.verify_packages()
    rel_plan.install_packages()
    rel_plan.copy_inst_hooks(args.dist)
    rel_plan.make_output()

    end_timestamp = datetime.datetime.now()
    duration = end_timestamp - start_timestamp

    if args.build_info:
        build_name = 'OPX'
        build_number = "{}.{}".format(
            rel_blueprint.output_format['version'],
            build_num
        )

        build_info = {
            "version": '1.0.1',
            "name": build_name,
            "number": build_number,
            "suffix": build_suffix,
            "type": 'GENERIC',
            "started": art8601_format(start_timestamp),
            "durationMillis": int(duration.total_seconds() * 1000),
            'modules': [
                {
                    'id': os.path.basename(args.b),
                    'artifacts': rel_plan.artifacts,
                    'dependencies': rel_plan.dependencies,
                },
            ],
            'properties': {
                "buildInfo.env." + key: val for key, val in os.environ.items()
            },
        }

        if args.build_url is not None:
            build_info['url'] = args.build_url
        if args.vcs_url is not None:
            build_info['vcsUrl'] = args.vcs_url
        if args.vcs_revision is not None:
            build_info['vcsRevision'] = args.vcs_revision

        with open(args.build_info, 'w') as f:
            json.dump(build_info, f, indent=4)

    return 0


if __name__ == "__main__":
    sys.exit(main())

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4 softtabstop=4 :
