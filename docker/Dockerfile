FROM debian:jessie-backports
LABEL maintainer="ops-dev@lists.openswitch.net"

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    apt-utils \
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
 && apt-get -t jessie-backports install -y gosu \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install requests-file

COPY entrypoint.sh /
COPY pbuilderrc /etc/pbuilderrc
COPY hook.d /var/cache/pbuilder/hook.d
RUN touch /mnt/Packages

ENV PATH $PATH:/mnt/opx-build/scripts

VOLUME /mnt
WORKDIR /mnt

