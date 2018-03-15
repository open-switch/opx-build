#!/bin/bash -eu

export DIST=${DEBIAN_DIST}

git-pbuilder create
git-pbuilder update
cat <<PBUILDER | git-pbuilder login --save-after-login
apt-get install -y curl eatmydata git python-pip

pip install pyang
ln -s /usr/local/bin/pyang /usr/bin

apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys AD5073F1

echo 'Package: *
Pin: origin ""
Pin-Priority: 1001
' >/etc/apt/preferences

echo "
deb     http://deb.openswitch.net/ $OPX_RELEASE main opx opx-non-free
deb-src http://deb.openswitch.net/ $OPX_RELEASE      opx
deb     http://deb.openswitch.net/contrib stable contrib
" | tee -a /etc/apt/sources.list
apt-get update
PBUILDER

