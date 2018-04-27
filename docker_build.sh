#!/bin/bash -e

DEFAULT_DIST=jessie
export DIST="${DIST:-$DEFAULT_DIST}"

# docker image tag
VERSION="$(git log -1 --pretty=%h)-${DIST}"
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

  docker build -t ${IMAGE}:base -f "Dockerfile-${DIST}" .
  pbuilder_create

  docker tag "${IMAGE}:${VERSION}" "${IMAGE}:${DIST}"

  if [[ "$DIST"b == "$DEFAULT_DIST"b ]]; then
    echo "Tagging as latest."
    docker tag "${IMAGE}:${VERSION}" "${IMAGE}:latest"
  fi
}

pbuilder_create() {
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

  docker run \
    --cidfile ${CIDFILE} \
    --privileged \
    --userns=host \
    -e ARCH=amd64 \
    -e DIST \
    "${IMAGE}:base" \
    /pbuilder_create.sh

  docker commit \
    --change 'CMD ["bash"]' \
    --change 'ENTRYPOINT ["/entrypoint.sh"]' \
    "$(cat ${CIDFILE})" \
    "${IMAGE}:${VERSION}"
}

main

