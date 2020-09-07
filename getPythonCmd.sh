#!/bin/bash

# Search for a compatible python version on the system or in the local path and return the path to
# it if found, otherwise returns nothing. The major version (e.g. python 3.x.x) must match.
# The minor and micro version must be compatible (e.g. actual must be newer or equal than the
# required)

set -euo pipefail

PYTHON_VERSION=${1-}
PYTHON_LOCAL_DIR=${2-}
PYTHON_MAJ_VERSION=${PYTHON_VERSION%%.*}        # strip minor and micro version
PYTHON_MIN_MICR_VERSION=${PYTHON_VERSION#*.}    # strip major version

compareVersionLte() {
    # returns 1 if the version $1 is less or equal than version $1
    [  "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}

if [ -z "${PYTHON_VERSION}" ]; then
    >&2 echo "First parameter missing"
    exit 1
fi

# shellcheck disable=SC2086
for TMP_PYTHON_CMD in $(find ${PATH//:/ } ${PYTHON_LOCAL_DIR} -maxdepth 1 -executable \
    -regextype sed -regex ".*/python3\.[0-9]*" 2> /dev/null | sort -V) ; do
    VERSION=$(${TMP_PYTHON_CMD} --version 2>&1 | awk  '{print $2}')
    # Check that the major version match
    if [ "${VERSION%%.*}" -ne "${PYTHON_MAJ_VERSION}" ]; then
        # Major version don't match, skip it
        continue
    #elif (( $(echo "${VERSION#*.} >= ${PYTHON_MIN_MICR_VERSION}" | bc -l) )); then
    elif compareVersionLte "${PYTHON_MIN_MICR_VERSION}" "${VERSION#*.}"; then
        # Major version match and the minor.micro is also compatible sets
        # the system python command.
        SYSTEM_PYTHON_CMD=${TMP_PYTHON_CMD}
        break
    fi
done

echo "${SYSTEM_PYTHON_CMD-}"
