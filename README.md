# OPX Build

This repository contains build information for OpenSwitch OPX Base.

If you would like to download binaries instead, see [Install OPX Base on Dell ON Series platforms](https://github.com/open-switch/opx-docs/wiki/Install-OPX-Base-on-Dell-ON-Series-platforms).

## Quick start

```bash
# get source code
repo init -u git://git.openswitch.net/opx/opx-manifest && repo sync

# build all open-source packages
opx-build/scripts/opx_run opx_build all

# assemble installer
opx-build/scripts/opx_run opx_rel_pkgasm.py -b opx-onie-installer/release_bp/OPX_dell_base.xml --dist unstable
```

## Getting started with OpenSwitch

### Prerequisites

- 20GB free disk space
- [Docker](https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/)
- [Repo](https://source.android.com/source/downloading)

### Get source code

```bash
repo init -u git://git.openswitch.net/opx/opx-manifest && repo sync
```

The `repo` commands download all of the source files that are necessary to build OpenSwitch. Beyond this, binary libraries for the SAI are also required. These binary libraries are currently *not* open source, as they are based on the Broadcom SDK.

### Build packages

By default, build dependencies are pulled from the `unstable` distribution. To change this, use `$OPX_DIST`.

```bash
# Build all repositories
opx-build/scripts/opx_run opx_build all

# Build a single repository (e.g., opx-logging)
opx-build/scripts/opx_run opx_build opx-logging

# Build multiple repositories
opx-build/scripts/opx_run opx_build opx-logging opx-nas-common

# Build against the testing distribution
OPX_DIST=testing opx-build/scripts/opx_run opx_build all
```

## Manual build of single repository

Sometimes, it is helpful to build a single repository with finer control.

It is always possible to enter the docker via opx_run, manually install prerequisite packages using "apt-get install" (for required Debian packages), "dpkg -i" (for required OPX packages), "pip install" (for required Python packages), etc., and run the command:

```bash
fakeroot debian/rules binary
```

This will allow you to see all files created during the build, such as object files, libtool files, C++ source and header files for Yang models, etc., that would normally be cleaned up after an opx_build build terminates.

It is possible to build unstripped executables by adding the following line to the end of the file debian/rules:

```
override_dh_strip:
```

## Installation

Creating an installer requires the [opx-onie-installer](http://git.openswitch.net/cgit/opx/opx-onie-installer/) repository. This repository is included if you cloned with `repo` and contains the blueprints used to assemble an installer.

Any local packages you have built will be included in the installer. To exclude them, remove the `deb` files from the repo root.

By default, the `unstable` distribution is used to grab missing packages on installer creation and fetch updates when running. To use a different distribution, use the `--dist` flag.

Run `opx-build/scripts/opx_run opx_rel_pkgasm.py --help` to see the available distributions.

```bash
opx-build/scripts/opx_run opx_rel_pkgasm.py -b opx-onie-installer/release_bp/OPX_dell_base.xml --dist stable
```

## Creating the opx-build Docker image

By default, build dependencies are pulled from the `unstable` distribution. To change this, use `$OPX_DIST`.

```bash
cd opx-build/docker
OPX_DIST=testing ./opx_setup
```

> [For older documentation, see b64c3be](https://github.com/open-switch/opx-build/blob/b64c3bedf6db0d5c5ed9fbe0e3ddcb5f4da3f525/README.md).

© 2017 Dell EMC
