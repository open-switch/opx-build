#!/bin/bash -e
#
# Copyright (c) 2015 Dell Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT
# LIMITATION ANY IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS
# FOR A PARTICULAR PURPOSE, MERCHANTABLITY OR NON-INFRINGEMENT.
#
# See the Apache Version 2.0 License for specific language governing
# permissions and limitations under the License.
#

# Available Options
OPX_DIST="${OPX_DIST-latest}"

# docker image name
image="opxhub/build"

CIDFILE=""
cleanup () {
  if [[ "${CIDFILE}b" != b ]] && [[ -e "${CIDFILE}" ]]; then
    docker rm -f "$(cat ${CIDFILE})"
    rm -f ${CIDFILE}
  fi
}
trap cleanup EXIT


main() {
  command -v docker >/dev/null 2>&1 || {
    echo "You will need to install docker for this to work."
    exit 1
  }

  case $OPX_DIST in
  base)
    build_base_layer
    ;;
  pbuilder)
    build_pbuilder_layer
    ;;
  latest)
    build_base_layer
    build_pbuilder_layer
    build_final_layer unstable
    ;;
  *)
    build_final_layer "$OPX_DIST"
    ;;
  esac

  echo "OPX Docker Images"
  docker ps -f ancestor=${image}:pbuilder
}

build_base_layer() {
  # As of this writing, commands requiring elevated privileges can't
  # be executed from within a Dockerfile. To work around this, first
  # create a base image, then the run privileged commands required to
  # finish provisioning it, finally tag the fully provisioned image.
  #
  # Cf. https://github.com/docker/docker/issues/1916
  docker build -t ${image}:base .
}

build_pbuilder_layer() {
  CIDFILE=id

  # Create the pbuilder chroot.
  #
  # Since pyang is not (yet) available as a debian package, install it
  # in the pbuilder chroot.
  #
  # There is an issue with docker/kernel/overlayfs/pbuilder: directory
  # renames fail with a cross-device link error if the directory is on
  # a lower layer. Work around this by combining all steps of chroot
  # creation in one docker run invocation.

  rm -f ${CIDFILE}
  docker run --cidfile ${CIDFILE} --privileged -e DIST=jessie ${image}:base sh -exc "
git-pbuilder create
git-pbuilder update
cat <<EOF | git-pbuilder login --save-after-login
apt-get install -y curl eatmydata git python-pip
pip install pyang
ln -s /usr/local/bin/pyang /usr/bin
apt-key adv --keyserver pgp.mit.edu --recv AD5073F1
echo '
Package: *
Pin: origin ''
Pin-Priority: 1001
' >/etc/apt/preferences
EOF"

  docker commit "$(cat ${CIDFILE})" "${image}:pbuilder"
}

build_final_layer() {
  opx_dist="${1-unstable}"
  CIDFILE=id
  rm -f ${CIDFILE}

  case $opx_dist in
    latest|unstable|testing|stable)
      docker run --cidfile ${CIDFILE} --privileged -e DIST=jessie ${image}:pbuilder sh -exc "
echo 'deb     http://deb.openswitch.net/ $opx_dist main opx opx-non-free' | tee -a /etc/apt/sources.list
echo 'deb-src http://deb.openswitch.net/ $opx_dist      opx' | tee -a /etc/apt/sources.list
cat <<EOF | git-pbuilder login --save-after-login
echo 'deb     http://deb.openswitch.net/ $opx_dist main opx opx-non-free' | tee -a /etc/apt/sources.list
echo 'deb-src http://deb.openswitch.net/ $opx_dist      opx' | tee -a /etc/apt/sources.list
EOF
apt-get update"
      ;;
    *)
      docker run --cidfile ${CIDFILE} --privileged -e DIST=jessie ${image}:pbuilder sh -exc "
echo 'deb http://deb.openswitch.net/ $opx_dist main opx opx-non-free' | tee -a /etc/apt/sources.list
cat <<EOF | git-pbuilder login --save-after-login
echo 'deb http://deb.openswitch.net/ $opx_dist main opx opx-non-free' | tee -a /etc/apt/sources.list
EOF
apt-get update"
      ;;
  esac

  docker commit --change 'CMD ["bash"]' --change 'ENTRYPOINT ["/entrypoint.sh"]' "$(cat ${CIDFILE})" "${image}:$opx_dist"

  if [ "$opx_dist"b = "unstable"b ]; then
    docker commit --change 'CMD ["bash"]' --change 'ENTRYPOINT ["/entrypoint.sh"]' "$(cat ${CIDFILE})" "${image}:latest"
  fi
}

main
