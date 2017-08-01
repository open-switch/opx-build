# opx-build

This repository contains build information for OpenSwitch OPX Base.

If you would like to download binaries instead, see [Install OpenSwitch OPX Base on Dell S6000 Platform](https://github.com/open-switch/opx-docs/wiki/Install-OPX-Base-on-Dell-S6000-ON-platform).

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

## Installation
Once all of the repositories have been built, an ONIE installer image can be created.  For example, to create an image for Dell platforms, run the command:

    opx-dev@077f7b30f8ef:/mnt# opx-build/scripts/opx_rel_pkgasm.py -b onie-opx-install/release_bp/OPX_dell_base.xml -n 1

<hr />

> For older documentation, see [b64c3be](https://github.com/open-switch/opx-build/blob/b64c3bedf6db0d5c5ed9fbe0e3ddcb5f4da3f525/README.md).

© 2017 Dell
