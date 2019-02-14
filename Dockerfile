FROM debian:stretch
LABEL maintainer="ops-dev@lists.openswitch.net"

ENV DIST stretch

RUN apt-get -qq update && apt-get -qq upgrade -y \
 && apt-get -qq install -y --no-install-recommends \
    build-essential \
    cowbuilder \
    curl \
    debian-archive-keyring \
    debootstrap \
    dh-autoreconf \
    dh-systemd \
    fakechroot \
    fakeroot \
    git-buildpackage \
    gosu \
    lsb-release \
    python-apt \
    python-jinja2 \
    python-lxml \
    python-pip \
    python-requests \
    sudo \
    vim \
    wget \
 && apt-get -qq autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Pyang not available as Debian package
RUN pip2 install pyang requests-file \
 && ln -s /usr/local/bin/pyang /usr/bin

# Get OPX and other Debian GPG keys
RUN gpg --batch --import /usr/share/keyrings/debian-archive-keyring.gpg \
 && gpg --batch --keyserver hkp://keyserver.ubuntu.com:80 --recv-key AD5073F1 \
 && gpg --batch --export AD5073F1 >/etc/apt/trusted.gpg.d/opx-archive-keyring.gpg

# Add OPX package sources
RUN mkdir -p /etc/apt/sources.list.d/ \
 && echo "deb http://deb.openswitch.net/$DIST unstable main opx opx-non-free" >>/etc/apt/sources.list.d/opx.list \
 && echo "deb-src http://deb.openswitch.net/$DIST unstable opx" >>/etc/apt/sources.list.d/opx.list \
 && apt-get -qq update

# Set up for the user we will create at runtime
RUN mkdir -p /home/opx && chmod -R 777 /home/opx \
 && echo 'opx ALL=(ALL) NOPASSWD:ALL' >>/etc/sudoers \
 && echo '%opx ALL=(ALL) NOPASSWD:ALL' >>/etc/sudoers \
 && echo 'Defaults env_keep += "OPX_RELEASE DIST ARCH"' >>/etc/sudoers

COPY assets/profile /etc/profile.d/opx.sh
COPY assets/entrypoint.sh /
COPY assets/hook.d /var/cache/pbuilder/hook.d
COPY assets/pbuilder_create.sh /
COPY assets/pbuilderrc /etc/pbuilderrc
COPY scripts /opt/opx-build/scripts

VOLUME /mnt
WORKDIR /mnt

# vim: syn=dockerfile
