#!/usr/bin/env python
"""
opx_bld_basics.py set of classes and defines intrinsic to the basic
                    OPX build environment
"""

from __future__ import print_function
import os
import fnmatch
import subprocess


class ChangeDirectory(object):
    """
    ChangeDirectory class for use as a context manager
        to perform operations in an alternate directory,
        encapsulates save of current directory, change to
        the alternative directory, and on exit of context
        return to the original working directory
    """
    def __init__(self, path):
        self.old_dir = os.getcwd()
        self.new_dir = path

    def __enter__(self):
        os.chdir(self.new_dir)

    def __exit__(self, exc_type, exc_value, exc_tb):
        os.chdir(self.old_dir)

        # Return correct value for python to raise
        #  an exception embedded in the context
        #  basically works now because default
        #  return for a function is None which
        #  evaluates to False
        if exc_type is None:
            return True
        return False


# This dictionary maps the blueprint platform attribute into
# the onie platform name.  The onie platform name is used as
# part of the image filenames.

ONIE_PLATFORM_MAP = {
    'S3048-ON': 'x86_64-dell_s3000_c2338-r0',
    'S6000-ON': 'x86_64-dell_s6000_s1220-r0',
    'S6000-VM': 'x86_64-dell_OPX_VM_s6000-r0',
    'ALL-X64':  'x86_64',
}

# need to harmonize with the above list
PLATFORMS = ONIE_PLATFORM_MAP.keys()
IMAGES = ['ALL-Base']
ARCHS = ['x86_64']

PUB_LOCS = {'latest': '/tftpboot/OPX',
            'archive': '/neteng/netarchive1/OPX'}
DEFAULT_PUB = 'latest'

DEV_RELEASE = 'engineering'
DEFAULT_RELEASE = DEV_RELEASE
RELEASE_DIRS = [DEV_RELEASE, 'testing']

# Dictonary maps release name to release specific
#  information. Should probably be replaced by an
#  independent database.
# NOTE: all release names must be listed above
#       This excludes the release "states", these
#       Will all be at a minimum in the testing
#       state (only one at at time), all others
#       will be stable + nmae
INACTIVE_STATES = ['deprecated', 'retired']
RELEASE_STATES = ['sid', 'unstable', 'testing', 'stable'] + INACTIVE_STATES

RELEASES = [
    { 'rel-name': 'OPX',
      'rel-version': '1.0.0',
      'rel-state': 'stable',
      'tool-sha': '6fff5835afc6ca9ee5abcc4f22a32aa7c44e56ad'
      }
]

RELEASES_BY_NAME = {_r['rel-name']: _r for _r in RELEASES}
RELEASES_BY_VERSION = {_r['rel-version']: _r for _r in RELEASES}

RELEASE_NAMES = [n_['rel-name'] for n_ in RELEASES] + RELEASE_DIRS


INST_GOOD_LINK = 'last_good'
INST_LINKS = ['latest', INST_GOOD_LINK]

DEFAULT_BUILDID = '99999'
DEFAULT_DIRNAME = 'latest-build'

VERBOSITY = 0


def release_path(publication=DEFAULT_PUB, release=DEFAULT_RELEASE):
    """
    release_path - return the path to installers
    input:
        publication - which of the published sets of installers
                        tftboot or archive (netarchive)
        release - which release build installers
    """
    assert release in RELEASE_NAMES

    path = PUB_LOCS[publication]

    if path is not None:
        if release in RELEASE_DIRS:
            rel_dir = '%s-release'
        else:
            rel_dir = 'release_%s-release'

        path = os.path.join(path, (rel_dir % release),
                            'AmazonInstallers')

    if release is not DEFAULT_RELEASE and VERBOSITY > 0:
        print('release path returns %s' % path)
    return path


def find_files(path='workspace/debian/jessie/x86_64/build', find='*.deb',
               out_filter='*-dev_*'):
    """
    find_files - find the files that match criteria and return the list
    input:
        path - where to start file tree walk
        find - regular expression of desired file name(s)
        out_filter - regular expression of file names to exclude
    return: list of file paths
    """
    flist = []

    for rdir, srdirs, files in os.walk(path):
        if VERBOSITY > 1:
            print("searching " + rdir)
            if VERBOSITY > 2:
                for _sd in srdirs:
                    print("  has subdir " + _sd)

        for fname in files:
            if fnmatch.fnmatch(fname, find):
                if out_filter is not None \
                        and fnmatch.fnmatch(fname, out_filter):
                    continue
                flist.append(os.path.join(rdir, fname))
                # consider making this an itterator/factory>
                #  return/pause until end -- can't recall what
                #  the patern name is right now

    return flist


def short_path(file_path):
    """
    short_path -- returns a single directory with file_name
    input:
        file_path - some portion of a file path name, may be
                    relative, but must exist
    returns: string <directory name><os path seperator><file name>
    diagnostic: raises exception if file not found
    """
    if not os.path.exists(file_path):
        raise NameError(('%s does not exist' % file_path))

    full_path = os.path.abspath(file_path)
    my_dir = os.path.basename(os.path.dirname(full_path))
    return os.path.join(my_dir, os.path.sep, os.path.basename(full_path))


def gen_package_list(pkg_cache_path):
    """
    gen_package_list -- generate a Packages and Packages.gz file from
                        the packages in the given path
    input:
        pkg_cache_path - Path to the folder containing the package cache
    returns: None
    diagnostic: raises exception if call to dpkg-scanpackages or gzip fails
    """
    packages_file = os.path.join(pkg_cache_path, 'Packages')
    packages_gz_file = os.path.join(pkg_cache_path, 'Packages.gz')

    # Create a package repository in the cache
    # Do the write first so the file exists,
    # or try read/write fails not found
    cmd = ['dpkg-scanpackages', '-m', '.', '/dev/null']
    with open(packages_file, 'w+') as fd_:
        try:
            subprocess.check_call(cmd, stdout=fd_,
                                  cwd=pkg_cache_path)
        except subprocess.CalledProcessError as ex:
            print(ex)
            raise

    # Add a gzipped version of Packages for use by apt-get
    cmd = ['gzip', '-9c']
    with open(packages_file, 'r') as fd_, \
            open(packages_gz_file, 'w') as fd0:
        try:
            subprocess.check_call(cmd, stdin=fd_, stdout=fd0,
                                  cwd=pkg_cache_path)
        except subprocess.CalledProcessError as ex:
            print(ex)
            raise


# set of support functions for RELEASES above

# pre-check for release name and version strings

def valid_rel_ver(version):
    """
    valid_rel_ver -- is the version string passed in valid
    """
    return version in RELEASES_BY_VERSION


def valid_rel_name(name):
    """
    valid_rel_name -- is the name string passed in valid
    """
    return name in RELEASES_BY_NAME


# active release names
def active_release_names():
    """
    Fetch all the active names
    """
    names = [n_['rel-name'] for n_ in RELEASES
                                if n_['rel-state'] is not 'retired']
    names = names + RELEASE_DIRS
    return names


# name query
def get_relname_info(name):
    """
    locates the name (row) in the release map defined above
    and returns that objects properties (columns)
    """
    return RELEASES_BY_NAME[name]


# version query
def get_relver_info(version):
    """
    As above, returns the row associated with the release
    version string specified

    Currently throws a key error if the version is not that
    of a release
    """
    return RELEASES_BY_VERSION[version]


# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4 softtabstop=4 :
