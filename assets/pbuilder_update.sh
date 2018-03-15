#!/bin/bash -eu

if [[ $# -eq 1 ]] && [[ "$1" != latest ]]; then
  OPX_RELEASE="$1"
else
  OPX_RELEASE="unstable"
fi
DEBIAN_DIST=${DEBIAN_DIST-jessie}

# Default pbuilder root builds against unstable
# I tried moving jessie to jessie_unstable, but it ballooned the image size by
# 500MB. This compromise keeps the image size down for a bit of added
# complexity.
if [[ "$OPX_RELEASE" == unstable ]]; then
  export DIST=$DEBIAN_DIST
else
  export DIST=${DEBIAN_DIST}_${OPX_RELEASE}
fi

debian_root="/var/cache/pbuilder/base-${DEBIAN_DIST}.cow"
opx_root="/var/cache/pbuilder/base-${DIST}.cow"

if [[ -d "$opx_root" ]]; then
  echo "[INFO] Pbuilder chroot for $DIST already exists."
else
  echo "[INFO] Creating $OPX_RELEASE chroot."

  cp -a "$debian_root" "$opx_root"

  cat <<PBUILDER | git-pbuilder login --save-after-login
sed -i '/deb.openswitch.net/d' /etc/apt/sources.list
echo "deb     http://deb.openswitch.net/ $OPX_RELEASE main opx opx-non-free" | tee -a /etc/apt/sources.list
[[ "$OPX_RELEASE" =~ ^(unstable|testing|stable)$ ]] && {
  echo "deb-src http://deb.openswitch.net/ $OPX_RELEASE      opx" | tee -a /etc/apt/sources.list
}
echo "deb     http://deb.openswitch.net/contrib stable contrib" | tee -a /etc/apt/sources.list
apt-get update
PBUILDER
fi

