#!/usr/bin/env python
"""
opx_get_packages -- fetch a list of debian packages, and all their
    run-time dependencies
"""

from __future__ import print_function
import apt
import apt_pkg
import collections
import sys
import os
import shutil
import subprocess
import argparse
import logging
import itertools
from distutils.version import LooseVersion

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# defaults for the OpxPackages constructor (__init__) function
#  also used in command invocation method below
DEFAULT_SYSROOT = "workspace/debian/jessie/x86_64/sysroot"
DEFAULT_SYSROOTDEV = None

DEFAULT_PKG_URL = "http://artifactory.force10networks.com/ar"
DEFAULT_PKG_DISTRIBUTION = "unstable"
DEFAULT_PKG_COMPONENT = "non-free"


class VersionWrapper(object):
    """
    :class:`apt_pkg.Version` wrapper

    We need to do set operations on :class:`apt_pkg.Version` objects,
    but they are not hashable.  This thin wrapper does just enough to
    make the objects hashable.
    """

    def __init__(self, version):
        self._ver = version

    def __hash__(self):
        return hash((self._ver.parent_pkg.name, self._ver.ver_str))

    def __eq__(self, other):
        return (self._ver.parent_pkg.name == other._ver.parent_pkg.name and
                self._ver.ver_str == other._ver.ver_str)

    def __str__(self):
        return self._ver.__str__()

    @property
    def parent_pkg(self):
        """
        apt Parent Package accessor
        """
        return self._ver.parent_pkg

    @property
    def ver_str(self):
        """
        apt Package Version string accessor
        """
        return self._ver.ver_str


class OpxPackagesError(Exception):
    """
    OpxPackgesError - OPX get package general exception
    """
    pass


class OpxPackageSource(object):
    """
    Represents package source (sources.list entry)
    """

    def __init__(self, url, distribution, component):
        """
        Construct a :class:`OpxPackageSource` object

        :param url:
          The url to the base of the package repository.

        :param distribution:
          The distribution (also called 'suite') reflects the
          level of testing/acceptance of a particular package.
          In the Debian package repository, packages start as
          unstable, and are promoted to testing, stable, and a
          release codename like 'wheezy' or 'jessie'.

        :param component:
          The component (also called 'section'). In the Debian
          package repository, component is 'main', 'contrib', or
          'non-free'. Other repositories have their own naming
          conventions.
        """
        self.url = url
        self.distribution = distribution
        self.component = component


class OpxPackages(object):
    """
    OpxPackages class -- Amazon River Packages class

    Provides interface to the python apt and apt_pkg libraries
    Used to fulfill build and dev dependencies for clone and
    clone-all actions.
    Will be used to assemble from packages
    """
    def __init__(self,
                 sysroot,
                 pkg_sources,
                 default_solver=False,
                 sysrootdev=None,
                 install_recommends=False,
                 install_suggests=False):
        """
        Construct a :class:`OpxPackages` object

        :param sysroot:
           Path to sysroot
        :param pkg_sources:
           List of :class:`OpxPackageSource` objects, used to create
           /etc/apt/sources.list file used to fetch packages.
        :param sysrootdev:
           Path to sysroot-dev
        :param install_recomends:
           If ``True``, install recommended packages.
        :param install_suggests:
           If ``True``, install suggested packages.
        """
        self._apt_cache = None
        self._cache = None
        self._default_solver = default_solver
        self._pkg_sources = pkg_sources
        self._folder = sysroot
        self._build_folder = sysrootdev

        if self._folder[-1:] == '/':
            self._folder = self._folder[:-1]

        if not os.path.exists(self._folder):
            raise OpxPackagesError(self._folder + " does not exist")

        _msg = "Sysroot is in " + self._folder
        if not self._build_folder:
            self._build_folder = self._folder + "-dev"

        if self._build_folder and os.path.exists(self._build_folder):
            _msg += " Development rootfs is in " + self._build_folder
        else:
            self._build_folder = None

        print(_msg)

        # Set up pointers to and create the dpkg package cache
        #  within the specified sysroot
        self._apt_cache = os.path.join(self._folder, "var", "lib", "dpkg")

        # Standard debian packages are maintained in a seperate root
        #  file system image to keep isolation between the AR
        #  generate package and the standard distribution packages
        #  Development packages from the distro are imported in
        #  a sysroot-dev root file system image with a package
        #  cache, that package cache is used to seed the sysroot
        #  for individual package build or development, so seed
        #  this sysroot's package cache from the sysroot-dev if
        #  it exists ...
        if self._build_folder:
            _build_cache = os.path.join(self._build_folder,
                                            "var", "lib", "dpkg")
            print("Checking..." + self._apt_cache + " and " + _build_cache)
            if not os.path.exists(self._apt_cache) \
                            and os.path.exists(_build_cache):
                print("Copying.. " + _build_cache)
                shutil.copytree(_build_cache, self._apt_cache, symlinks=True)

        self._apt_cache = os.path.join(self._folder, "var", "cache",
                                                        "apt", "archives")
        self.sources = os.path.join(self._folder, "etc", "apt", "sources.list")
        if not os.path.exists(self.sources):
            if not os.path.exists(os.path.dirname(self.sources)):
                os.makedirs(os.path.dirname(self.sources))
        else:
            shutil.copy(self.sources, self.sources + ".save")

        # create sources.list file with url, distribution, and component.
        with open(self.sources, "w") as f:
            for pkg_source in self._pkg_sources:
                print("Using %s %s %s" % (pkg_source.url,
                                          pkg_source.distribution,
                                          pkg_source.component))
                f.write("deb [arch=amd64] %s %s %s\n" % (pkg_source.url,
                                            pkg_source.distribution,
                                            pkg_source.component))

        # create cache and update it
        self._cache = apt.Cache(rootdir=self._folder, memonly=True)

        # set Install-Recommends and Install-Suggests configuration options
        apt_pkg.config['APT::Install-Recommends'] = \
            "1" if install_recommends else "0"
        apt_pkg.config['APT::Install-Suggests'] = \
            "1" if install_suggests else "0"

        try:
            self._cache.update()
        except Exception as ex:
            print("\nCache update error ignored : %s\n" % (ex))

        self._cache.open()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        """
        close and clean-up of an object instance
        """
        self._cache.close()
        if os.path.exists(self.sources + '.save'):
            shutil.copy(self.sources + ".save", self.sources)

    def list_packages(self):
        """
        List packages available in cache
        """

        print("Packages available are as follows:")
        for i in self._cache.keys():
            print(str(i))

    @property
    def _depcache(self):
        """
        Dependency cache state accessor
        """
        return self._cache._depcache

    def _dump_package(self, pkg):
        """
        dump_package

        dump metadata from :class:`apt_pkg.Package` object
        """

        logger.debug("%s:", pkg.name)
        logger.debug("  marked_delete:     %s",
                     self._depcache.marked_delete(pkg))
        logger.debug("  marked_downgrade:  %s",
                     self._depcache.marked_downgrade(pkg))
        logger.debug("  marked_install:    %s",
                     self._depcache.marked_install(pkg))
        logger.debug("  marked_keep:       %s",
                     self._depcache.marked_keep(pkg))
        logger.debug("  marked_reinstall:  %s",
                     self._depcache.marked_reinstall(pkg))
        logger.debug("  marked_upgrade:    %s",
                     self._depcache.marked_upgrade(pkg))
        logger.debug("  is_auto_installed: %s",
                     self._depcache.is_auto_installed(pkg))
        logger.debug("  is_garbage:        %s",
                     self._depcache.is_garbage(pkg))
        logger.debug("  is_inst_broken:    %s",
                     self._depcache.is_inst_broken(pkg))
        logger.debug("  is_now_broken:     %s",
                     self._depcache.is_now_broken(pkg))
        logger.debug("  is_upgradable      %s",
                     self._depcache.is_upgradable(pkg))

    def _fetch_package(self, pkg, from_user=False, backtrace=[]):
        """
        Get the dependencies of the package's desired (candidate)
        version and compute the set of dependent packages. If the
        dependent package is not already installed, recursively
        invoke this function.

        :meth:`apt_pkg.Dependency.all_targets` returns the set of
        dependent package versions that that satisfy a dependency.
        However, since a package may have more than one dependency
        for a given dependent package (e.g., one dependency with a
        version floor, another with a version ceiling), we compute
        the set of dependent packages which satisfy all of the
        dependencies.

        This is done with two dictionaries.  pkg_versions is the
        dictionary of all dependent packages and versions, while
        dep_versions is the dictionary of packages and versions
        for a single :class:`apt.pkg.Dependency`.

        TODO: This function only handles simple dependencies,
        not Breaks, Conflicts, or Replaces.
        """

        version = self._depcache.get_candidate_ver(pkg)
        logger.debug("version: %s", version)
        logger.debug("    %s", backtrace)

        if 'Depends' in version.depends_list:
            pkg_versions = dict()
            for or_deps in version.depends_list["Depends"]:
                logger.debug("or_deps: %s", or_deps)

                # In general, this script does not handle "or"
                # dependencies. However, We have special cased
                # makedev/udev and debconf/debconf-2.0 to make
                # it good enough for NGOS image creation until
                # it can.
                if len(or_deps) != 1:
                    logger.debug("pre: %s", or_deps)
                    or_deps = [dep for dep in or_deps
                               if dep.target_pkg.name
                                    not in ('makedev', 'debconf-2.0')]
                    logger.debug("post: %s", or_deps)

                if len(or_deps) != 1:
                    raise OpxPackagesError("Can't handle or-dependencies")

                for dep in or_deps:
                    logger.debug("dep: %s", dep)

                    logger.debug("%s is satisfied by:", dep.target_pkg.name)
                    for v in dep.all_targets():
                        logger.debug("    %s", v)

                    dep_versions = collections.defaultdict(set)
                    for v in dep.all_targets():
                        dep_versions[dep.target_pkg.name].add(VersionWrapper(v))

                for name, versions in dep_versions.items():
                    if not name in pkg_versions:
                        pkg_versions[name] = set(versions)
                    else:
                        pkg_versions[name] &= versions

            # We now have list of :class:`apt_pkg.Version` objects that satisfy
            # the dependencies for the package.  Next we identify what packages
            # may need to be installed.
            for name, versions in pkg_versions.items():
                logger.debug("pkg_versions: %s -> %s", pkg.name, name)
                if len(versions) == 0:
                    raise OpxPackagesError(
                        "Unable to satisfy dependency: %s %s" %
                        (pkg.name, name))

                # Identify a list of candidate packages
                logger.debug("start iterating group")
                candidate_versions = []
                sv = sorted(versions, key=lambda x: x._ver.parent_pkg.name)
                for k, vx in itertools.groupby(sv,
                                        key=lambda x: x._ver.parent_pkg.name):
                    # change vx from an iterator to a list, as we need to
                    # traverse it multiple times
                    vx = list(vx)

                    # While the library returns the versions in order, the
                    # set operations destroy that order.  So use the Loose
                    # Version() function from distutils to sort
                    best_v = sorted(vx,
                                    key=lambda x: LooseVersion(x.ver_str),
                                    reverse=True)

                    logger.debug("%s", k)
                    for v in best_v:
                        logger.debug("    %s", v.ver_str)

                    best_v = best_v[0]
                    logger.debug("best candidate is %s", best_v)
                    candidate_versions.append(best_v)
                logger.debug("done iterating group")

                # Determine whether any of the candidates are already installed
                installed = False
                for v in candidate_versions:
                    dep_pkg = v.parent_pkg
                    if dep_pkg.id in [xpkg.id for xpkg in backtrace]:
                        installed = True
                        break
                    if dep_pkg.current_state != apt_pkg.CURSTATE_NOT_INSTALLED:
                        installed = True
                        break
                    if self._depcache.marked_install(dep_pkg):
                        installed = True
                        break

                # If dependent package is not installed, then select the first
                # (we don't have a mechanism to indicate a preference), then
                # recurse.
                if not installed:
                    v = candidate_versions[0]

                    logger.debug("\t will fetch %s %s",
                                 v.parent_pkg.name, v.ver_str)

                    self._depcache.set_candidate_ver(dep_pkg, v._ver)
                    self._fetch_package(dep_pkg, backtrace=[pkg]+backtrace)

        logger.debug("marking %s for install", pkg)

        try:
            self._depcache.mark_install(pkg, False, from_user)
        except SystemError as ex:
            raise OpxPackagesError, OpxPackagesError(ex), sys.exc_info()[2]

    def fetch(self, names):
        """
        Fetch packages

        Fetch specified and all dependent packages.
        """

        # There may be more than one revision specification for a package.
        # We store them in a list for each package, and we store each list
        # in a ordered dict indexed by the package name. An orderd dict is
        # used to ensure the packages are processed in the specified order.

        depends = collections.OrderedDict()
        for package_name in names:
            pkg = apt_pkg.parse_depends(package_name)[0][0]
            if pkg[0] not in depends:
                depends[pkg[0]] = []
            depends[pkg[0]].append(pkg)

        for package_name in depends.keys():
            try:
                pkg = self._cache[package_name]
            except KeyError:
                msg = "Can't find %s in package cache" % package_name
                raise OpxPackagesError, OpxPackagesError(msg), sys.exc_info()[2]

            # find a version that satisfies the revision specification
            found = False
            for v in pkg.versions:
                satisfied = True

                for dep in depends[package_name]:
                    dep_version = dep[1]
                    dep_relation = dep[2]

                    if not apt_pkg.check_dep(v.version,
                                             dep_relation,
                                             dep_version):
                        satisfied = False
                        break

                if satisfied:
                    found = True

                    pkg.candidate = v
                    if self._default_solver:
                        # Use default apt_pkg solver
                        try:
                            pkg.mark_install(auto_inst=True,
                                             auto_fix=True,
                                             from_user=False)
                        except SystemError as ex:
                            raise OpxPackagesError, OpxPackagesError(ex), sys.exc_info()[2]

                        if pkg.marked_keep and not pkg.is_installed:
                            self._dump_package(pkg._pkg)
                            msg = "Could not install %s due to version conflicts" % package_name
                            raise OpxPackagesError(msg)
                    else:
                        # Use modified solver for handling semantic versioning
                        self._fetch_package(pkg._pkg)

                    break

            if not found:
                raise OpxPackagesError("Failed to locate %s that satisfies revision specifications" % package_name)

        if self._depcache.broken_count:
            logger.info("Attempting to fix %s broken packages",
                        self._depcache.broken_count)
            try:
                self._depcache.fix_broken()
            except SystemError:
                raise OpxPackagesError("We have broken dependencies")

        # Fetch packages
        try:
            self._cache.fetch_archives()
        except apt.cache.FetchFailedException as ex:
            # re-raise exception
            msg = "Fetch failed"
            raise OpxPackagesError, OpxPackagesError(msg), sys.exc_info()[2]
        except apt.cache.FetchCancelledException as ex:
            # re-raise exception
            msg = "Fetch cancelled"
            raise OpxPackagesError, OpxPackagesError(msg), sys.exc_info()[2]

    def install(self):
        """
        Install packages

        Install packages in the package cache.
        """
        for debfile in [os.path.join(self._apt_cache, f)
                        for f in os.listdir(self._apt_cache)
                                    if f.endswith('.deb')]:

            l = ["dpkg", "-x", debfile, self._folder]
            print(l)
            try:
                subprocess.check_call(l)
            except subprocess.CalledProcessError as ex:
                logger.error("dpkg -x %s failed", debfile)
                logger.exception(ex)

    def clean(self):
        """
        Remove files from package cache
        """
        for debfile in [os.path.join(self._apt_cache, f)
                        for f in os.listdir(self._apt_cache)
                                    if f.endswith('.deb')]:
            os.remove(debfile)


def main():
    """ Command line class instantiation
    the class instance is created based on defaults
    and any command line requested options
    """

    # parse command line arguments.
    #
    # _distribution_ and _component_ select the hierarchy within the
    # package repository. In an official Debian OS repository,
    # _distribution_ names a archive type/state like "unstable" or
    # "testing" or a OS codename like "jessie"; and _component_ is
    # "main", "contrib", or "non-free". Other package repositories
    # use different naming conventions.

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug',
                        help=argparse.SUPPRESS,
                        action='store_true')
    parser.add_argument('--install-recommends',
                        dest='install_recommends',
                        help='Consider recommended packages as dependencies for installing',
                        action='store_true')
    parser.add_argument('--no-install-recommends',
                        dest='install_recommends',
                        help=argparse.SUPPRESS,
                        action='store_false')
    parser.add_argument('--install-suggests',
                        dest='install_suggests',
                        help='Consider suggested packages as dependencies for installing',
                        action='store_true')
    parser.add_argument('--no-install-suggests',
                        dest='install_suggests',
                        help=argparse.SUPPRESS,
                        action='store_false')
    parser.add_argument('--download-only', '-d',
                        help='Download packages, but do not unpack or install them',
                        action='store_true')
    parser.add_argument('-l', '--sysroot',
                        help="specify system root directory",
                        default=DEFAULT_SYSROOT)
    parser.add_argument('-L', '--sysrootdev',
                        help="specify development system root directory",
                        default=DEFAULT_SYSROOTDEV)
    parser.add_argument('-u', '--url',
                        help="package repository URL",
                        default=DEFAULT_PKG_URL)
    parser.add_argument('--distribution',
                        help="package distribution",
                        default=DEFAULT_PKG_DISTRIBUTION)
    parser.add_argument('--component',
                        help="package component",
                        default=DEFAULT_PKG_COMPONENT)
    parser.add_argument('-p', '--package_list',
                        help="comma separated list of packages")
    parser.add_argument('--default_solver', action='store_true',
                        help="Use standard solver to resolve package dependencies")

    args = parser.parse_args()

    if args.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.WARNING

    logging.basicConfig(level=loglevel)

    # instantiate this OpxPackage instance
    try:
        with OpxPackages(sysroot=args.sysroot,
                        pkg_sources=[
                            OpxPackageSource(args.url,
                                            args.distribution,
                                            args.component),
                        ],
                        default_solver=args.default_solver,
                        sysrootdev=args.sysrootdev,
                        install_recommends=args.install_recommends,
                        install_suggests=args.install_suggests) as ar:

            if args.package_list:
                ar.fetch(names=args.package_list.split(','))
                if not args.download_only:
                    ar.install()
            else:
                ar.list_packages()

    except OpxPackagesError as ex:
        print(ex)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4 softtabstop=4 :
