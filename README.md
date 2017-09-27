# opx-build

This repository contains build information for OpenSwitch OPX Base.

If you would like to download binaries instead, see [Install OPX Base on Dell ON Series platforms](https://github.com/open-switch/opx-docs/wiki/Install-OPX-Base-on-Dell-ON-Series-platforms).

## Getting Started with OpenSwitch

### Prerequisites

- 20GB free disk space
- [Docker](https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/)
- [Repo](https://source.android.com/source/downloading)

### Download Source Code and Create Docker Image

```bash
# Clone repositories
repo init -u git://git.openswitch.net/opx/opx-manifest && repo sync

# Build docker image
pushd opx-build/scripts
./opx_setup
popd
```

The `repo` commands download all of the source files that are necessary to build OpenSwitch. Beyond this, binary libraries for the SAI are also required. These binary libraries are currently *not* open source, as they are based on the SDK from Broadcom.

### Build Packages

```bash
# Build all repositories
./opx-build/scripts/opx_run /bin/bash -ci "cd /mnt && opx-build/scripts/opx_build all"

# Build a single repository (e.g., opx-logging)
./opx-build/scripts/opx_run /bin/bash -ci "cd /mnt && opx-build/scripts/opx_build opx-logging"
```

Building multiple packages with the Docker image created from `opx_setup` requires building each package in dependency order. An error with the missing packages will be thrown if packages are built out of dependency order. Building all packages is often quicker and easier.

```bash
# Build multiple repositories (e.g., opx-logging and opx-common-utils)
./opx-build/scripts/opx_run
opx-dev@a51b0642125f:/$ cd /mnt
opx-dev@a51b0642125f:/mnt$ opx-build/scripts/opx_build opx-logging
opx-dev@a51b0642125f:/mnt$ opx-build/scripts/opx_build opx-common-utils
```

To build a single package out of dependency order, a different Docker image must be used. This image can be built by running `opx_setup` on the `feature/fetch-prerequisites` branch of `opx-build`, or by using the image stored in our [Bintray repository](https://bintray.com/dell-networking/opx-docker/opx%3Aopx-build). This image variant will fetch prerequisite packages from Bintray.

```bash
# Build opx-nas-l2
docker pull dell-networking-docker-opx-docker.bintray.io/opx/opx-build:fetch
docker tag -f dell-networking-docker-opx-docker.bintray.io/opx/opx-build:fetch docker-opx:latest
./opx-build/scripts/opx_run /bin/bash -ci "cd /mnt && opx-build/scripts/opx_build opx-nas-l2"
```

## Installation
Once all of the repositories have been built, an ONIE installer image can be created.  For example, to create an image for Dell platforms, run the command:

```bash
opx-build/scripts/opx_rel_pkgasm.py -b onie-opx-installer/release_bp/OPX_dell_base.xml -n 1
```

<hr />

> For older documentation, see [b64c3be](https://github.com/open-switch/opx-build/blob/b64c3bedf6db0d5c5ed9fbe0e3ddcb5f4da3f525/README.md).

© 2017 Dell EMC
