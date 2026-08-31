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

[ -z "${FEDORA_IMAGE}" ] && echo "Set the env variable FEDORA_IMAGE" && exit 1
[ -z "${FEDORA_VERSION}" ] && echo "Set the env variable FEDORA_VERSION" && exit 1
[ -z "${CPU_ARCH}" ] && echo "Set the env variable CPU_ARCH" && exit 1

BUILD_DIR="fedora_build_${CPU_ARCH}"
CLOUD_INIT_ISO="cidata.iso"
NAME="fedora${FEDORA_VERSION}"
FEDORA_CONTAINER_IMAGE="localhost/fedora:${FEDORA_VERSION}-${CPU_ARCH}"

IMAGE_BUILD_CMD=$(which podman 2>/dev/null || which docker)
if [ -z $IMAGE_BUILD_CMD ]; then
    echo "No podman or docker installed"
    exit 1
fi

case "$CPU_ARCH" in
    "amd64")
        CPU_ARCH_CODE="x86_64"
        VIRT_TYPE="kvm"
        BOOT_OPTS=""
	;;
    "arm64")
        CPU_ARCH_CODE="aarch64"
        VIRT_TYPE="qemu"
        # aarch64 requires UEFI and a writable per-VM NVRAM vars file.
        # Without the vars file libvirt cannot configure ACPI on aarch64.
        AARCH64_VARS="/tmp/aavmf-vars-${NAME}.fd"
        for vars_path in \
            "/usr/share/edk2/aarch64/vars-template-pflash.qcow2" \
            "/usr/share/AAVMF/AAVMF_VARS.fd"; do
            if [ -f "${vars_path}" ]; then
                cp "${vars_path}" "${AARCH64_VARS}"
                break
            fi
        done
        if [ ! -f "${AARCH64_VARS}" ]; then
            echo "ERROR: No aarch64 UEFI vars template found. Install qemu-efi-aarch64."
            exit 1
        fi
        BOOT_OPTS="--boot uefi,nvram=${AARCH64_VARS}"
 ;;
    "s390x")
        CPU_ARCH_CODE="s390x"
        VIRT_TYPE="qemu"
        BOOT_OPTS=""
	;;
    *)
        echo "Use the value amd64, s390x or arm64 for CPU_ARCH env variable"
        exit 1
	;;
esac

if [ "$FULL_EMULATION" = "true" ]; then
    VIRT_TYPE="qemu"
fi

# When no secrets are available, the password cannot be computed.
# Running such an option can be useful on CI when the build is validated.
if [ "${NO_SECRETS}" != "true" ]; then
    set +x
    FEDORA_PASSWORD=$(uv run get_fedora_password.py)
    PASSWORD_PLACEHOLDER="CHANGE_ME"
    sed -i "s/password: $PASSWORD_PLACEHOLDER/password: $FEDORA_PASSWORD/" user-data
    set -x
else
    echo "NO_SECRETS set: skipping Fedora password injection"
fi

echo "Create cloud-init user data ISO"
cloud-localds $CLOUD_INIT_ISO user-data

# When running on CI, the latest Fedora may not be yet supported by virt-install
# therefore use a lower one. It should have no influence on the result.
OS_VARIANT=$NAME
if [ $FEDORA_VERSION -gt 40 ]; then
   OS_VARIANT="fedora40"
fi

# Work on a copy of the base image so the original is never mutated.
# This ensures cloud-init always runs fresh on repeated executions.
WORK_IMAGE="${FEDORA_IMAGE%.qcow2}-work.qcow2"
cp "${FEDORA_IMAGE}" "${WORK_IMAGE}"


# Clean up any leftovers from a previous failed run
rm -rf $BUILD_DIR
if virsh domstate "${NAME}" &>/dev/null; then
    echo "Found existing domain '${NAME}', removing it before proceeding..."
    virsh destroy "${NAME}" 2>/dev/null || true
    if [ "${CPU_ARCH}" = "arm64" ]; then
        virsh undefine --nvram "${NAME}"
    else
        virsh undefine "${NAME}"
    fi
fi

CONSOLE_LOG="/tmp/console-${NAME}.log"
# Pre-create the log file with open permissions so the qemu process can write to it
touch "${CONSOLE_LOG}"
chmod 666 "${CONSOLE_LOG}"
echo "Run the VM (ctrl+] to exit)"
# shellcheck disable=SC2086
virt-install \
  --memory 2048 \
  --vcpus 2 \
  --arch $CPU_ARCH_CODE \
  --name $NAME \
  --disk $WORK_IMAGE,device=disk \
  --disk $CLOUD_INIT_ISO,device=cdrom \
  --os-variant $OS_VARIANT \
  --virt-type $VIRT_TYPE \
  --graphics none \
  --network default \
  --noautoconsole \
  --serial file,path="${CONSOLE_LOG}" \
  $BOOT_OPTS \
  --import

# Stream the guest serial console log to stdout so CI logs show what is happening inside the VM.
# tail -f works without a TTY and streams as lines are written by the guest.
tail -f "${CONSOLE_LOG}" &
CONSOLE_PID=$!

# Wait for cloud-init to finish (user-data issues 'shutdown' as its last step).
# virsh domstate exits non-zero for unknown domains, so we treat that as "shut off" too.
echo "Waiting for VM to shut down after cloud-init completes..."
WAIT_SECONDS=0
PERIOD_SECONDS=60
TIMEOUT_SECONDS=1800
while true; do
    DOMAIN_STATE=$(virsh domstate "${NAME}" 2>&1) || true
    if [ "${DOMAIN_STATE}" = "shut off" ] || echo "${DOMAIN_STATE}" | grep -q "failed to get domain"; then
        break
    fi
    if [ ${WAIT_SECONDS} -ge ${TIMEOUT_SECONDS} ]; then
        echo "ERROR: VM did not shut down within ${TIMEOUT_SECONDS} seconds (last state: ${DOMAIN_STATE})"
        exit 1
    fi
    sleep ${PERIOD_SECONDS}
    WAIT_SECONDS=$((WAIT_SECONDS + PERIOD_SECONDS))
done
echo "VM shut down after ${WAIT_SECONDS} seconds"
# Stop the console tailer and clean up temp files
kill "${CONSOLE_PID}" 2>/dev/null || true
rm -f "${CONSOLE_LOG}" "${AARCH64_VARS:-}"

# Prepare VM image
virt-sysprep -d "${NAME}" --operations machine-id,bash-history,logfiles,tmp-files,net-hostname,net-hwaddr

echo "Remove Fedora VM"
if [ $CPU_ARCH = "arm64" ]; then
    virsh undefine --nvram "${NAME}"
else
    virsh undefine "${NAME}"
fi

# Ensures the 'fedora' pool is destroyed to prevent hanging on subsequent executions
virsh pool-destroy fedora

rm -f "${CLOUD_INIT_ISO}"

mkdir $BUILD_DIR
echo "Snapshot image"
qemu-img convert -c -O qcow2 "${WORK_IMAGE}" "${BUILD_DIR}/${FEDORA_IMAGE}"

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
