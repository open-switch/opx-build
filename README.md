# opx-build

This repository contains build information for OpenSwitch OPX Base. See [Install OPX Base on Dell ON-Series platforms](https://github.com/open-switch/opx-docs/wiki/Install-OPX-Base-on-Dell-ON-Series-platforms) to download binaries.

## Getting started with OpenSwitch

### Prerequisites

- 20GB free disk space
- [Docker](https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/)
- [Repo](https://source.android.com/source/downloading)

### Download source code and create Docker image

```bash
# Clone repositories
repo init -u git://git.openswitch.net/opx/opx-manifest && repo sync

# Build docker image
pushd opx-build/scripts
./opx_setup
popd
```

The `repo` commands download all of the source files that are necessary to build OpenSwitch. Beyond this, binary libraries for the SAI are also required. These binary libraries are currently *not* open source, as they are based on the SDK from Broadcom.

### Build packages

```bash
# Build all repositories
./opx-build/scripts/opx_run /bin/bash -ci "cd /mnt && opx-build/scripts/opx_build all"

# Build a single repository (e.g., opx-logging)
./opx-build/scripts/opx_run /bin/bash -ci "cd /mnt && opx-build/scripts/opx_build opx-logging"
```

## Installation
Once all of the repositories have been built, an ONIE installer image can be created.  For example, to create an image for Dell platforms, run the command:

    opx-build/scripts/opx_rel_pkgasm.py -b onie-opx-installer/release_bp/OPX_dell_base.xml -n 1

<hr />

See [b64c3be](https://github.com/open-switch/opx-build/blob/b64c3bedf6db0d5c5ed9fbe0e3ddcb5f4da3f525/README.md) for older documentation.

© 2017 Dell EMC
