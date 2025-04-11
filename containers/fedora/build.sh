#!/usr/bin/env bash
set -xe

# Function to restore the password placeholder
cleanup() {
    if [ -f user-data ] && [ -n "$FEDORA_PASSWORD" ]; then
        sed -i "s/password: $FEDORA_PASSWORD/password: $PASSWORD_PLACEHOLDER/" user-data
    fi
}
trap cleanup EXIT

[ -z "${FEDORA_IMAGE}" ] && echo "Set the env variable FEDORA_IMAGE" && exit 1
[ -z "${FEDORA_VERSION}" ] && echo "Set the env variable FEDORA_VERSION" && exit 1
[ -z "${CPU_ARCH}" ] && echo "Set the env variable CPU_ARCH" && exit 1

BUILD_DIR="fedora_build"
CLOUD_INIT_ISO="cidata.iso"
NAME="fedora${FEDORA_VERSION}"
FEDORA_CONTAINER_IMAGE="localhost/fedora:${FEDORA_VERSION}-${CPU_ARCH}"

IMAGE_BUILD_CMD=$(which podman 2>/dev/null || which docker)
if [ -z $IMAGE_BUILD_CMD ]; then
    echo "No podman or docker installed"
    exit 1
fi

if [ $CPU_ARCH = "amd64" ]; then
    CPU_ARCH_CODE="x86_64"
    VIRT_TYPE="kvm"
elif [ $CPU_ARCH = "arm64" ]; then
    CPU_ARCH_CODE="aarch64"
    VIRT_TYPE="qemu"
elif [ $CPU_ARCH = "s390x" ]; then
    CPU_ARCH_CODE="s390x"
    VIRT_TYPE="qemu"
else
    echo "Use the value amd64, s390x or arm64 for CPU_ARCH env variable"
    exit 1
fi

FEDORA_PASSWORD=$(uv run get_fedora_password.py)
PASSWORD_PLACEHOLDER="CHANGE_ME"
sed -i "s/password: $PASSWORD_PLACEHOLDER/password: $FEDORA_PASSWORD/" user-data

echo "Create cloud-init user data ISO"
cloud-localds $CLOUD_INIT_ISO user-data

echo "Run the VM (ctrl+] to exit)"
virt-install \
  --memory 2048 \
  --vcpus 2 \
  --arch $CPU_ARCH_CODE \
  --name $NAME \
  --disk $FEDORA_IMAGE,device=disk \
  --disk $CLOUD_INIT_ISO,device=cdrom \
  --os-variant $NAME \
  --virt-type $VIRT_TYPE \
  --graphics none \
  --network default \
  --import

echo "Stop Fedora VM"
virsh destroy "${NAME}" || true

# Prepare VM image
virt-sysprep -d "${NAME}" --operations machine-id,bash-history,logfiles,tmp-files,net-hostname,net-hwaddr

echo "Remove Fedora VM"
if [ $CPU_ARCH = "arm64" ]; then
    virsh undefine --nvram "${NAME}"
else
    virsh undefine "${NAME}"
fi

rm -f "${CLOUD_INIT_ISO}"

mkdir $BUILD_DIR
echo "Snapshot image"
qemu-img convert -c -O qcow2 "${FEDORA_IMAGE}" "${BUILD_DIR}/${FEDORA_IMAGE}"

echo "Create Dockerfile"

cat <<EOF > "${BUILD_DIR}/Dockerfile"
FROM scratch
COPY --chown=107:107 ${FEDORA_IMAGE} /disk/
EOF

pushd "${BUILD_DIR}"
echo "Build container image"
${IMAGE_BUILD_CMD} build -f Dockerfile --arch="${CPU_ARCH}" -t "${FEDORA_CONTAINER_IMAGE}" .

echo "Save container image as TAR"
${IMAGE_BUILD_CMD} save --output "fedora${FEDORA_VERSION}-${CPU_ARCH}.tar" "${FEDORA_CONTAINER_IMAGE}"
popd
echo "Fedora image located in ${BUILD_DIR}/"
