FROM debian:jessie
MAINTAINER ops-dev@lists.openswitch.net

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
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install requests-file

# Install gosu utility for use in entrypoint script
#
# Since gosu is not available as a package in jessie (it is in stretch),
# we need to fetch the binary from github. If the container is switched
# to stretch (even if OPX continues to target jessie), we can use the
# package instead.
#
ENV GOSU_VERSION 1.9
RUN set -x \
 && wget -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture)" \
 && wget -O /usr/local/bin/gosu.asc "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-$(dpkg --print-architecture).asc" \
 && export GNUPGHOME="$(mktemp -d)" \
 && gpg --keyserver ha.pool.sks-keyservers.net --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
 && gpg --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu \
 && rm -r "$GNUPGHOME" /usr/local/bin/gosu.asc \
 && chmod +x /usr/local/bin/gosu \
 && gosu nobody true

COPY entrypoint.sh /
COPY pbuilderrc /etc/pbuilderrc
COPY D05update-deps /var/cache/pbuilder/hook.d/
RUN touch /var/cache/pbuilder/result/Packages
