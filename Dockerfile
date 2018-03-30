FROM debian:jessie-backports
LABEL maintainer="ops-dev@lists.openswitch.net"

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    apt-utils \
    curl \
    dh-autoreconf \
    dh-systemd \
    fakechroot \
    git-buildpackage \
    lsb-release \
    python-apt \
    python-jinja2 \
    python-lxml \
    python-pip \
    python-requests \
    vim \
    wget \
 && apt-get -t jessie-backports install -y gosu

RUN pip2 install --upgrade pip \
 && pip2 install pyang requests-file \
 && ln -s /usr/local/bin/pyang /usr/bin \
 && touch /mnt/Packages \
 && echo "deb     http://deb.openswitch.net/ unstable main opx opx-non-free" | tee -a /etc/apt/sources.list \
 && echo "deb-src http://deb.openswitch.net/ unstable      opx" | tee -a /etc/apt/sources.list \
 && apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys AD5073F1 \
 && apt-get update \
 && mkdir -p /home/opx \
 && chmod -R 777 /home/opx

ENV PATH /opt/opx-build/scripts:/mnt/opx-build/scripts:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY scripts /opt/opx-build/scripts
COPY assets/bash_profile /home/opx/.bash_profile
COPY assets/entrypoint.sh /
COPY assets/hook.d /var/cache/pbuilder/hook.d
COPY assets/pbuilder_create.sh /
COPY assets/pbuilder_update.sh /
COPY assets/pbuilderrc /etc/pbuilderrc

VOLUME /mnt
WORKDIR /mnt

