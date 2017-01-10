Welcome to Openswitch Build System
==================================

Get Openswitch
---------------
There are two ways to get image:

- **Download and install binaries** - TBD, **or**
- **Build from scratch** - see the step-by-step instructions below to build the project.
 
Build environment recommendations
---------------------------------
- Intel multi-core
- Ubuntu 16.04 or later (desktop edition with Python installed)
- 20G available free disk space

The build environment
----------------------
### Prerequisites

Updated environment: `sudo apt-get update`
- GIT: `sudo apt-get install git`
- Repo: See http://source.android.com/source/downloading.html to install the **repo** tool.
```
    Make sure you have a bin/ directory in your home directory and that it is included in your path:
    $ mkdir ~/bin
    $ PATH=~/bin:$PATH
    Download the Repo tool and ensure that it is executable:
    $ curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
    $ chmod a+x ~/bin/repo
```
- apt-utils: `sudo apt-get install apt-utils`
- See [Docker environment setup guide](https://docs.docker.com/engine/installation/linux/ubuntulinux/) for complete information.
```
    sudo apt-get install linux-image-extra-$(uname -r) linux-image-extra-virtual
    sudo apt-key adv --keyserver hkp://ha.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
    sudo apt-add-repository 'deb https://apt.dockerproject.org/repo ubuntu-xenial main'
    sudo apt-get update
    apt-cache policy docker-engine
    sudo apt-get install -y docker-engine
    sudo service docker start
```
- To avoid running docker commands as root (with sudo):
```
    sudo groupadd docker ### The 'docker' group might already exist
    sudo gpasswd -a ${USER} docker ### Add your user id to the 'docker' group
    sudo service docker restart
```
- You may have to log out/in to activate the changes to groups   
- Ensure you have proper permissions to clone source file (ssh keys must be installed)

> **NOTE**: Setup your ssh keys with Github [Settings->keys](https://github.com/settings/keys) - we are using git over ssh. 

Clone the source code
---------------------
To get the source files for the Openswitch (opx*) repos, run the commands in an empty directory (root directory). For example *~/dev/opx/*:
```
    repo init -u ssh://git@github.com/open-switch/opx-manifest.git
    repo sync
```

The **repo sync** command downloads all of the source files that you need to build the openswitch. In addition to the source files, you will also need some binary libraries for the SAI. The SAI is currently not open sourced entirely, as it is based on Broadcom's SDK and no open source SAI implementation available from Broadcom at this time.

All the build scripts are found in the [opx_build repo](https://github.com/open-switch/opx-build) and will be downloaded as part of the above **repo sync**.

Openswitch Docker environment
----------------------------
To setup your Docker OPX image, use the script in the *opx-build/scripts* folder called **opx_setup**. This script builds a docker container called **docker-opx**, which will be used by the build scripts:
```
    cd opx-build/scripts/
    opx_setup
```

Build single repository
-------------------------
Goto root directory, where you have installed OPX repos and run OPX Docker container. 
```
    cd ~/dev/opx
    docker run --privileged -i -t -v ${PWD}:/mnt docker-opx:latest
```

Setup pbuilder environment inside docker container.
```
    root@077f7b30f8ef:/# DIST=jessie git-pbuilder create
```

To build a single repo, goto the repo and build. For example, to build opx_logging:
```
    root@077f7b30f8ef:/# cd /mnt/opx-logging
    root@077f7b30f8ef:/mnt/opx-logging# git-buildpackage --git-dist=jessie  --git-ignore-branch --git-pbuilder
```

Build ALL repositories
----------------------
TBD

Installation
------------
Once all of the repos have been built, you can install the created ONIE Debian x86_64 image. You can then install all of the build packages, along with the other Debian files you downloaded earlier in the root directory.

-TBD

(c) Dell 2016