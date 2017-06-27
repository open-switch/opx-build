#! /usr/bin/python

"""Create/update root file system image

A utility class used to create and update a root file system image,
using a previously created tar archive as a base.

Ideally we would create the root file system image from scratch. But
it's created using debootstrap in a docker container, which we can't
(reasonably) do here. It's worth investigating whether we can get the
same results using a different method.

See the open-source-rootfs repository for details.
"""

from __future__ import print_function
import hashlib
import sys
import os
import stat
import shutil
import subprocess
import requests
import requests_file
import tempfile

verbosity = 1

FAKECHROOT = 'fakechroot'
FAKEROOT = 'fakeroot'

class TemporaryDirectory(object):
    """
    Context Manager for managing lifetime of a temporary directory

    This was inspired by Python 3's tempfile.TemporaryDirectory
    class.
    """
    def __init__(self, suffix="", prefix="tmp", dir=None):
        self.closed = False
        self.name = tempfile.mkdtemp(suffix, prefix, dir)

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        self.cleanup()

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if not self.closed:
            try:
                shutil.rmtree(self.name)
            except:
                pass
            self.closed = True

class OpxrootfsError(Exception):
    pass

class Opxrootfs(object):
    """
    OPX root file system class

    Allows creation of a rootfs image from a tar archive, which can
    then be manipulated with various methods inspired by libguestfs.
    """
    @staticmethod
    def _my_mkdir(path):
        """
        Local make dir that takes into account the fact that
         it may already exist, or be a regular file
        elevated verbosity puts informational messages on stderr,
        present, but not a directory -- raise an error
        """
        if not os.path.isdir(path):
            if os.path.exists(path):
                if verbosity > 0:
                    print(path + " exists -- aborting", file=sys.stderr)
                raise
            try:
                os.makedirs(path)
            except OSError as exception:
                if exception.errno != os.errno.EEXIST:
                    raise
        elif verbosity > 0:
            print(path + " already exists", file=sys.stderr)

    def __init__(self, rootfs_path, rootfs_url, rootfs_sha1=None, rootfs_md5=None):
        """
        Initialize the rootfs instance
        Creates a root file system in the specified directory,
         with the appropriate properties for the work at hand

        :param:`rootfs_path`
           location of rootfs
        :param:`rootfs_url`
           url to initial rootfs location
        :param:`rootfs_sha1`
           SHA1 digest of rootfs tarball
        :param:`rootfs_md5`
           MD5 digest of rootfs tarball
        """

        # Create temporary file for fakeroot state
        self._fakeroot_state = tempfile.NamedTemporaryFile()

        # Create temporary directory for rootfs
        # if rootfs_path is None, use a temporary directory;
        # otherwise use the supplied path.
        if rootfs_path is None:
            self._rootfs_tmpdir = TemporaryDirectory()
            self._rootpath = self._rootfs_tmpdir.name
        else:
            self._rootpath = rootfs_path
            shutil.rmtree(self._rootpath, ignore_errors=True)
            self._my_mkdir(self._rootpath)

        # Use temporary file to hold incoming rootfs tar
        with tempfile.NamedTemporaryFile() as fd_:
            # request the specified archive
            print("fetching %s ..." % rootfs_url)

            s = requests.Session()
            s.mount('file://', requests_file.FileAdapter())

            resp = s.get(rootfs_url, stream=True)
            if not resp.status_code == requests.codes.ok:
                print(".remote fetch failed for %s : %d."
                      % (rootfs_url, resp.status_code),
                      file=sys.stderr)
                print(resp.headers['status'], file=sys.stderr)
                resp.raise_for_status()

            chunk_size = 4096
            md5 = hashlib.md5()
            sha1 = hashlib.sha1()
            for chunk in resp.iter_content(chunk_size):
                md5.update(chunk)
                sha1.update(chunk)
                fd_.write(chunk)
            fd_.flush()

            # Validate MD5 digest
            if rootfs_md5:
                if rootfs_md5 != md5.hexdigest():
                    raise OpxrootfsError("MD5 validation failed: got %s, expected %s"
                        % (md5.hexdigest(), rootfs_md5))

            # Validate SHA1 digest
            if rootfs_sha1:
                if rootfs_sha1 != sha1.hexdigest():
                    raise OpxrootfsError("SHA1 validation failed: got %s, expected %s"
                        % (sha1.hexdigest(), rootfs_sha1))

            # load the initial file system
            self.tar_in(fd_.name)

    def rootpath(self, *args):
        """
        Return host path to the rootfs path :param:`path`.
        """

        path = self._rootpath
        for x in args:
            if not path.endswith('/') and not x.startswith('/'):
                path += '/'
            path += x

        return path

    def exists(self, path):
        """
        Returns true if :param:`path` exists

        .. note::

           since this only determines whether the file exists, we should not
           have to do this under fakeroot.
        """
        return os.path.exists(self.rootpath(path))

    def isfile(self, path):
        """
        Returns true if :param:`path` is a regular file.

        .. note::

           since this only determines the file type, we should not have
           to do this under fakeroot.
        """
        return os.path.isfile(self.rootpath(path))

    def isdir(self, path):
        """
        Returns true if :param:`path` is a directory.

        .. note::

           since this only determines the file type, we should not have
           to do this under fakeroot.
        """
        return os.path.isdir(self.rootpath(path))

    def listdir(self, path):
        """
        Returns a list of the names of the directory entries in the
        directory given by path.

        .. note::
           since this only returns names, we should not have to do
           this under fakeroot.
        """
        return os.listdir(self.rootpath(path))

    def compute_md5(self, path):
        """
        Returns hashlib.md5 object of file given path path.


        .. note::
           since this only accesses file contents, we should not
           have to do this under fakeroot.
        """
        with open(self.rootpath(path), 'rb') as f:
            md5 = hashlib.md5()
            buf = f.read(8192)
            while len(buf) > 0:
                md5.update(buf)
                buf = f.read(8192)

        return md5

    def compute_sha1(self, path):
        """
        Returns hashlib.sha1 object of file given path path.


        .. note::
           since this only accesses file contents, we should not
           have to do this under fakeroot.
        """
        with open(self.rootpath(path), 'rb') as f:
            sha1 = hashlib.sha1()
            buf = f.read(8192)
            while len(buf) > 0:
                sha1.update(buf)
                buf = f.read(8192)

        return sha1

    def remove(self, path):
        """
        Removes file or directory :param:`path`.

        .. note::
           Run under fakeroot to keep database coherent.
        """
        cmd = [FAKEROOT,
               '-i', self._fakeroot_state.name,
               '-s', self._fakeroot_state.name,
               'rm', '-f', self.rootpath(path)
        ]

        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as ex:
            if verbosity > 0:
                print(ex)
            raise OpxrootfsError("Can't remove(%s)" % path)

    def rename(self, src, dst):
        """
        Rename file or directory :param:`src` to :param:`dst`.

        .. note::
           Run under fakeroot to keep database coherent.
        """
        cmd = [FAKEROOT,
               '-i', self._fakeroot_state.name,
               '-s', self._fakeroot_state.name,
               'mv', '-f', self.rootpath(src), self.rootpath(dst)
        ]

        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as ex:
            if verbosity > 0:
                print(ex)
            raise OpxrootfsError("Can't rename(%s,%s)" % (src, dst))

    def rmtree(self, path):
        """
        Recursively directory :param:`path` and its contents.

        .. note::
           Run under fakeroot to keep database coherent.
        """
        cmd = [FAKEROOT,
               '-i', self._fakeroot_state.name,
               '-s', self._fakeroot_state.name,
               'rm', '-rf', self.rootpath(path)
        ]

        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as ex:
            if verbosity > 0:
                print(ex)
            raise OpxrootfsError("Can't rmtree(%s)" % path)

    def do_chroot(self, op_path):
        """
        Execute file specified under fakechroot in this
         rootfs instance, ...
        """
        print("do_chroot(self, %s)" % op_path)

        # do we need to verify the path, as in a file
        #  referenced by the path
        # copy the file, and insure execute permission
        _target = os.path.join(self._rootpath, os.path.basename(op_path))
        shutil.copyfile(op_path, _target)
        os.chmod(_target, (stat.S_IXUSR | stat.S_IRUSR
                            | stat.S_IXGRP | stat.S_IRGRP
                            | stat.S_IXOTH | stat.S_IROTH))

        # build up the fakeroot/fakechroot wrapper for the command
        #  assumes the command is in the root directory, and
        #  thus executes it there.
        cmd = [FAKECHROOT]
        cmd += [FAKEROOT,
                '-i', self._fakeroot_state.name,
                '-s', self._fakeroot_state.name]
        cmd += ['/usr/sbin/chroot', self._rootpath]
        cmd += [os.path.sep + os.path.basename(op_path)]

        if verbosity > 0:
            print("do_chroot")
            print(cmd)

        # execute the command in the fakechroot environment
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as ex:
            if verbosity > 0:
                print(ex)
            raise OpxrootfsError("Can't run script")

        # collect status for return/display
        # need to remove the command executed from the sysroot
        os.remove(os.path.join(self._rootpath, os.path.basename(op_path)))

    def installed_packages(self):
        """
        Returns a list of installed packages within the rootfs
        """
        print("installed_packages(self)")

        # Build up the fakeroot/fakechroot wrapper for the apt list command
        cmd = [FAKECHROOT, FAKEROOT, '/usr/sbin/chroot']
        cmd += [self._rootpath, 'apt', 'list', '--installed']

        if verbosity > 0:
            print("installed_packages")
            print(cmd)

        package_list = []
        # execute the command in the fakechroot environment and get the output
        try:
            for pkg_full in subprocess.check_output(cmd).split('\n'):
                # An installed package has the form
                # util-linux/stable,now 2.25.2-6 amd64 [installed]
                # We only care about the package name (before the /)
                pkg = pkg_full.split('/')[0]
                package_list.append(pkg)
        except subprocess.CalledProcessError as ex:
            if verbosity > 0:
                print(ex)
            raise OpxrootfsError("Error running apt list")

        # Return the installed package list to the caller
        return package_list

    def tar_in(self, tarfile, directory='/', compress=True):
        """
        Extract a compressed tar archive to the rootfs

        Extracts a tar archive from local file :param:`tarfile` into
        rootfs directory :param:`directory`.
        """
        if verbosity > 0:
            print("tar_in(self, %s, %s)" % (tarfile, directory))

        tar_cmd = ['tar', '-C', self.rootpath(directory), '-x', '-f', '-']

        if compress:
            tar_cmd += ['-z']

        if verbosity > 1:
            tar_cmd += ['-v']

        tar_cmd += ['--numeric-owner', '--preserve-permissions']

        with open(tarfile, 'r') as fd_:
            cmd = [FAKEROOT,
                    '-i', self._fakeroot_state.name,
                    '-s', self._fakeroot_state.name]
            cmd += tar_cmd

            if verbosity > 0:
                print("tar_in(%s)" % cmd)

            try:
                subprocess.check_call(cmd, stdin=fd_)
            except subprocess.CalledProcessError as ex:
                if verbosity > 0:
                    print(ex)
                raise OpxrootfsError("Can't extract tarball")

    def tar_out(self, tarfile, directory='/', compress=True, files=['.']):
        """
        Create a compressed tar archive from the rootfs

        Creates a tar archive with the contents of :param:`directory`
        and writes it to local file :param:`tarfile`.
        """
        if verbosity > 0:
            print("tar_out(self, %s, %s)" % (tarfile, directory))

        tar_cmd = ['tar', '-C', directory, '-c', '-f', '-']

        if compress:
            tar_cmd += ['-z']

        if verbosity > 1:
            tar_cmd += ['-v']

        tar_cmd += files

        with open(tarfile, 'w') as fd_:
            cmd = [FAKECHROOT, '-e', 'none']
            cmd += [FAKEROOT,
                    '-i', self._fakeroot_state.name,
                    '-s', self._fakeroot_state.name]
            cmd += ['/usr/sbin/chroot', self._rootpath]
            cmd += tar_cmd

            if verbosity > 0:
                print("tar_out(%s)" % cmd)

            try:
                subprocess.check_call(cmd, stdout=fd_)
            except subprocess.CalledProcessError as ex:
                if verbosity > 0:
                    print(ex)
                raise OpxrootfsError("Can't create tarball")

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4 softtabstop=4 :
