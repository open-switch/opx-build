#! /bin/bash

if [ -n "${LOCAL_UID}" ]; then
    LOCAL_GID=${LOCAL_GID:-${LOCAL_UID}}

    groupadd -o --gid=${LOCAL_GID} opx-dev
    useradd -o --uid=${LOCAL_UID} --gid=${LOCAL_GID} -s /bin/bash opx-dev
    echo '%opx-dev ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

    exec gosu opx-dev "$@"
fi

exec "$@"
