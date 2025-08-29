#!/usr/bin/env bash
set -xe

# Function to restore the password placeholder
cleanup() {
    set +x
    if [ -f user-data ] && [ -n "$FEDORA_PASSWORD" ]; then
        sed -i "s/password: $FEDORA_PASSWORD/password: $PASSWORD_PLACEHOLDER/" user-data
    fi
    set -x
}
trap cleanup EXIT

[ -z "${CPU_ARCH}" ] && echo "Set the env variable CPU_ARCH" && exit 1
[ -z "${PR_NUMBER}" ] && echo "Missing PR number from github action component-builder.yml" && exit 1

FEDORA_VARS_FILE=fedora-vars
FEDORA_VERSION=$(sed -n "s/^FEDORA_VERSION:[[:space:]]\(.*\)/\1/pi" ${FEDORA_VARS_FILE})
FEDORA_IMAGE=$(sed -n "s/^FEDORA_${CPU_ARCH}_IMAGE:[[:space:]]\(.*\)/\1/pi" ${FEDORA_VARS_FILE})
BUILD_DIR="fedora_build"
CLOUD_INIT_ISO="cidata.iso"
NAME="fedora${FEDORA_VERSION}"
FEDORA_CONTAINER_IMAGE="localhost/fedora:${FEDORA_VERSION}-${CPU_ARCH}"
FEDORA_QUAY_STAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:${FEDORA_VERSION}-${CPU_ARCH}-pr-${PR_NUMBER}"
NO_SECURE_BOOT=""
IMAGE_BUILD_CMD=$(which podman 2>/dev/null)

if [ -z ${IMAGE_BUILD_CMD} ]; then
    echo "No podman installed"
    exit 1
fi

case "${CPU_ARCH}" in
    "x86_64")
        CPU_ARCH_CODE="amd64"
        VIRT_TYPE="kvm"
	;;
    "aarch64")
        CPU_ARCH_CODE="arm64"
        NO_SECURE_BOOT="--boot uefi,firmware.feature0.name=secure-boot,firmware.feature0.enabled=no"
        VIRT_TYPE="qemu"
	;;
    "s390x")
        CPU_ARCH_CODE="s390x"
        VIRT_TYPE="qemu"
	;;
    *)
        echo "Use the value x86_64, aarch64 or s390x for CPU_ARCH env variable"
        exit 1
	;;
esac

if [ "${FULL_EMULATION}" = "true" ]; then
    VIRT_TYPE="qemu"
fi

# When no secrets are available, the password cannot be computed.
# Running such an option can be useful on CI when the build is validated.
if [ "${NO_SECRETS}" != "true" ]; then
    set +x
    FEDORA_PASSWORD=$(uv run get_fedora_password.py)
    PASSWORD_PLACEHOLDER="CHANGE_ME"
    esc_pw="$(printf '%s' "${FEDORA_PASSWORD}" | sed -e 's/[\/&]/\\&/g')"
    sed -i "s/password: ${PASSWORD_PLACEHOLDER}/password: ${esc_pw}/" user-data
    set -x
else
    echo "NO_SECRETS set: skipping Fedora password injection"
fi

echo "Create cloud-init user data ISO"
cloud-localds ${CLOUD_INIT_ISO} user-data

# When running on CI, the latest Fedora may not be yet supported by virt-install
# therefore use a lower one. It should have no influence on the result.
OS_VARIANT=$NAME
vers_num="${FEDORA_VERSION%%[^0-9]*}"
if [ -n "${vers_num}" ] && [ "${vers_num}" -gt 40 ] 2>/dev/null; then
   OS_VARIANT="fedora40"
fi

echo "Run the VM (ctrl+] to exit)"
virt-install \
  --memory 4096 \
  --vcpus 2 \
  --arch ${CPU_ARCH} \
  --name ${NAME} \
  --disk ${FEDORA_IMAGE},device=disk \
  --disk ${CLOUD_INIT_ISO},device=cdrom \
  --os-variant ${OS_VARIANT} \
  --virt-type ${VIRT_TYPE} \
  --graphics none \
  --network default \
  --noautoconsole \
  --wait 40 \
  ${NO_SECURE_BOOT} \
  --import

# Prepare VM image
virt-sysprep -d "${NAME}" --operations machine-id,bash-history,logfiles,tmp-files,net-hostname,net-hwaddr

echo "Remove Fedora VM"
if [ "${CPU_ARCH}" = "s390x" ]; then
    virsh undefine "${NAME}"
else
    virsh undefine --nvram "${NAME}"
fi

rm -f "${CLOUD_INIT_ISO}"

mkdir -p ${BUILD_DIR}
echo "Snapshot image"
qemu-img convert -c -O qcow2 "${FEDORA_IMAGE}" "${BUILD_DIR}/${FEDORA_IMAGE}"

echo "Create Dockerfile"

cat <<EOF > "${BUILD_DIR}/Dockerfile"
FROM scratch
COPY --chown=107:107 ${FEDORA_IMAGE} /disk/
EOF

pushd "${BUILD_DIR}"
echo "Build container image"
${IMAGE_BUILD_CMD} build -f Dockerfile --arch="${CPU_ARCH_CODE}" -t "${FEDORA_CONTAINER_IMAGE}" .

# Tag the image
${IMAGE_BUILD_CMD} tag "${FEDORA_CONTAINER_IMAGE}" "${FEDORA_QUAY_STAGE}"

echo "Save container image as TAR"
${IMAGE_BUILD_CMD} save --output "fedora-image-${CPU_ARCH}.tar" "${FEDORA_QUAY_STAGE}"
popd
echo "Fedora image located in ${BUILD_DIR}/"
