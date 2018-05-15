#!/bin/bash -eu

mkdir -p "/mnt/pool/${DIST}-${ARCH}" && touch "/mnt/pool/${DIST}-${ARCH}/Packages"

git-pbuilder create
git-pbuilder update
cat <<PBUILDER | git-pbuilder login --save-after-login
apt-get install -y curl git python-lxml python-pip

pip install pyang
ln -s /usr/local/bin/pyang /usr/bin

echo 'Package: *
Pin: origin ""
Pin-Priority: 1001
' >/etc/apt/preferences
PBUILDER

