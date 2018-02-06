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
 && apt-get -t jessie-backports install -y gosu \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install requests-file

COPY assets/entrypoint.sh /
COPY assets/pbuilderrc /etc/pbuilderrc
COPY assets/hook.d /var/cache/pbuilder/hook.d
RUN touch /mnt/Packages

RUN curl -fsSL https://bintray.com/user/downloadSubjectPublicKey?username=dell-networking | apt-key add -
RUN curl -fsSL https://bintray.com/user/downloadSubjectPublicKey?username=open-switch | apt-key add -

ENV PATH $PATH:/opt/opx-build/scripts:/mnt/opx-build/scripts

COPY scripts /opt/opx-build/scripts

RUN mkdir -p /home/opx
RUN chmod -R 777 /home/opx
RUN echo 'export PATH=$PATH:/opt/opx-build/scripts:/mnt/opx-build/scripts' >> /home/opx/.bash_profile

VOLUME /mnt
WORKDIR /mnt

