# OPX Build

This repository contains build information for OpenSwitch OPX Base.

If you would like to download binaries instead, see [Install OPX Base on Dell ON Series platforms](https://github.com/open-switch/opx-docs/wiki/Install-OPX-Base-on-Dell-ON-Series-platforms).

## Quick start

```bash
# get source code
repo init -u git://git.openswitch.net/opx/opx-manifest && repo sync

# build all open-source packages
opx-build/scripts/opx_run opx_build all

# index local packages for installer
opx-build/scripts/idx-pkgs

# assemble installer
opx-build/scripts/opx_run opx_rel_pkgasm.py -b opx-onie-installer/release_bp/OPX_dell_base.xml --local-opx-pkgs
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

```bash
# Build all repositories
opx-build/scripts/opx_run opx_build all

# Build a single repository (e.g., opx-logging)
opx-build/scripts/opx_run opx_build opx-logging
```

Building multiple packages with the Docker image created from `opx_setup` requires building each package in dependency order. An error with the missing packages will be thrown if packages are built out of dependency order. Building all packages is often quicker and easier.

```bash
# Build multiple repositories (e.g., opx-logging and opx-common-utils)
opx-build/scripts/opx_run
opx-dev@a51b0642125f:/mnt$ opx_build opx-logging
opx-dev@a51b0642125f:/mnt$ opx_build opx-common-utils
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

Once all of the repositories have been built, an ONIE installer image can be created.  For example, to create an image for Dell platforms from local packages, run these commands:

```bash
# index local packages for installer (optional)
opx-build/scripts/idx-pkgs

# assemble installer
opx-build/scripts/opx_run opx_rel_pkgasm.py -b opx-onie-installer/release_bp/OPX_dell_base.xml --local-opx-pkgs
```

If you would like to assemble an installer from downloaded packages, you can skip building all together. This will download packages from Bintray instead of using local packages.

```bash
opx-build/scripts/opx_run opx_rel_pkgasm.py -b opx-onie-installer/release_bp/OPX_dell_base.xml
```

## Creating the opx-build Docker image

```bash
cd opx-build/docker
./opx_setup
```

> [For older documentation, see b64c3be](https://github.com/open-switch/opx-build/blob/b64c3bedf6db0d5c5ed9fbe0e3ddcb5f4da3f525/README.md).

© 2017 Dell EMC
