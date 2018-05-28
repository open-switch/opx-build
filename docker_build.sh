#!/bin/bash -e
# Currently includes jessie and stretch pbuilder roots

# docker image tag
VERSION="$(git log -1 --pretty=%h)"
# docker image name
IMAGE="opxhub/build"
# file where container id is saved for cleanup
CIDFILE=".cid"

cleanup () {
  if [[ -e "${CIDFILE}" ]]; then
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

  docker build -t ${IMAGE}:base .
  pbuilder_create jessie base stamp1
  pbuilder_create stretch stamp1 "${VERSION}"
  docker tag "${IMAGE}:${VERSION}" "${IMAGE}:latest"
}

pbuilder_create() {
  # Create the pbuilder chroots.
  #
  # Since pyang is not (yet) available as a debian package, install it
  # in the pbuilder chroot.
  #
  # There is an issue with docker/kernel/overlayfs/pbuilder: directory
  # renames fail with a cross-device link error if the directory is on
  # a lower layer. Work around this by combining all steps of chroot
  # creation in one docker run invocation.
  [[ $# != 3 ]] && return 1

  dist="$1"
  from_tag="$2"
  to_tag="$3"

  rm -f ${CIDFILE}

  docker run \
    --cidfile ${CIDFILE} \
    --privileged \
    -e ARCH=amd64 \
    -e DIST="$dist" \
    "${IMAGE}:${from_tag}" \
    /pbuilder_create.sh

  docker commit \
    --change 'CMD ["bash"]' \
    --change 'ENTRYPOINT ["/entrypoint.sh"]' \
    "$(cat ${CIDFILE})" \
    "${IMAGE}:${to_tag}"

  docker rm -f "$(cat $CIDFILE)"
  rm -f ${CIDFILE}
}

main

