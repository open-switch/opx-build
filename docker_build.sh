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
OPX_DIST="${OPX_DIST-unstable}"

# docker image name
build="opxhub/build"

CIDFILE=""
cleanup () {
  if [[ "${CIDFILE}b" != b ]] && [[ -e "${CIDFILE}" ]]; then
    docker rm -f "$(cat ${CIDFILE})"
    rm -f ${CIDFILE}
  fi
  docker rmi -f ${build}:base
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || {
  echo "You will need to install docker for this to work."
  exit 1
}

if [ "$(docker ps -f ancestor=${build}:latest --format "{{.ID}}")b" = b ] ; then
  CIDFILE=id

  # As of this writing, commands requiring elevated privileges can't
  # be executed from within a Dockerfile. To work around this, first
  # create a base image, then the run privileged commands required to
  # finish provisioning it, finally tag the fully provisioned image.
  #
  # Cf. https://github.com/docker/docker/issues/1916

  docker build -t ${build}:base .

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
  docker run --cidfile ${CIDFILE} --privileged -e DIST=jessie ${build}:base sh -c '
git-pbuilder create
git-pbuilder update
echo "
  apt-get install -y curl eatmydata git python-pip
  pip install pyang
  ln -s /usr/local/bin/pyang /usr/bin
  curl -fsSL https://bintray.com/user/downloadSubjectPublicKey?username=dell-networking | apt-key add -
  curl -fsSL https://bintray.com/user/downloadSubjectPublicKey?username=open-switch | apt-key add -
  echo "deb http://dell-networking.bintray.com/opx-apt '"$OPX_DIST"' main" | tee -a /etc/apt/sources.list
  echo "deb http://dl.bintray.com/open-switch/opx-apt '"$OPX_DIST"' main" | tee -a /etc/apt/sources.list
  cat >/etc/apt/preferences <<EOF
Package: *
Pin: origin ""
Pin-Priority: 1001
EOF
" | git-pbuilder login --save-after-login'
  docker commit --change 'CMD ["bash"]' --change 'ENTRYPOINT ["/entrypoint.sh"]' "$(cat ${CIDFILE})" "${build}:$OPX_DIST"
  if [ "$OPX_DIST"b = "unstable"b ]; then
    docker commit --change 'CMD ["bash"]' --change 'ENTRYPOINT ["/entrypoint.sh"]' "$(cat ${CIDFILE})" "${build}:latest"
  fi
fi

echo "OPX Docker Image"
docker ps -f ancestor=${build}:latest
