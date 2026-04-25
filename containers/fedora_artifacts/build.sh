#!/usr/bin/env bash
#
# Build base Fedora disk artifacts (qcow2, raw, .gz, .xz) for a given version.
# Output goes to containers/fedora_artifacts/out/ for upload to Artifactory.
#
# Usage:
#   FEDORA_VERSION=41-1.4 ./build.sh
#   ./build.sh 43-1.6
#
# Requires: wget, qemu-img, gzip, xz, sha256sum
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/out"
FEDORA_VERSION="${FEDORA_VERSION:-${1:-}}"

if [[ -z "${FEDORA_VERSION}" ]]; then
  echo "Usage: FEDORA_VERSION=41-1.4 ./build.sh   OR   ./build.sh 41-1.4" >&2
  exit 1
fi

MAJOR_VERSION="${FEDORA_VERSION%%-*}"
BASE="Fedora-Cloud-Base-Generic-${FEDORA_VERSION}"
rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

download_and_build_arch() {
  local arch="$1"
  local url_base="$2"
  local qcow2_name="${BASE}.${arch}.qcow2"
  local raw_name="${BASE}.${arch}.raw"
  local img_name="Fedora-qcow2-${arch}.img"
  local checksum_file="Fedora-Cloud-${FEDORA_VERSION}-${arch}-CHECKSUM"

  echo "[${arch}] Downloading base qcow2..."
  wget -q -O "${OUT_DIR}/${qcow2_name}" "${url_base}/${qcow2_name}"

  echo "[${arch}] Downloading checksum file..."
  wget -q -O "${OUT_DIR}/${checksum_file}" "${url_base}/${checksum_file}"
  echo "[${arch}] Verifying SHA256 checksum..."
  local expected_hash actual_hash
  expected_hash=$(grep "SHA256 (${qcow2_name})" "${OUT_DIR}/${checksum_file}" | awk -F' = ' '{print $2}')
  actual_hash=$(sha256sum "${OUT_DIR}/${qcow2_name}" | awk '{print $1}')
  if [[ -z "${expected_hash}" ]]; then
    echo "[${arch}] WARNING: Could not find checksum for ${qcow2_name} in ${checksum_file}" >&2
    exit 1
  fi
  if [[ "${expected_hash}" != "${actual_hash}" ]]; then
    echo "[${arch}] CHECKSUM MISMATCH for ${qcow2_name}!" >&2
    echo "  Expected: ${expected_hash}" >&2
    echo "  Got:      ${actual_hash}" >&2
    exit 1
  fi
  echo "[${arch}] Checksum OK."

  echo "[${arch}] Creating raw..."
  qemu-img convert -O raw "${OUT_DIR}/${qcow2_name}" "${OUT_DIR}/${raw_name}"

  echo "[${arch}] Creating raw.gz and raw.xz..."
  gzip -k "${OUT_DIR}/${raw_name}"
  xz -k "${OUT_DIR}/${raw_name}"

  echo "[${arch}] Creating qcow2.gz and qcow2.xz..."
  gzip -k "${OUT_DIR}/${qcow2_name}"
  xz -k "${OUT_DIR}/${qcow2_name}"

  echo "[${arch}] Renaming qcow2 to ${img_name}..."
  mv "${OUT_DIR}/${qcow2_name}" "${OUT_DIR}/${img_name}"
}

# x86_64 and aarch64: primary Fedora mirror
# s390x: fedora-secondary
echo "Building Fedora ${FEDORA_VERSION} artifacts for x86_64, aarch64, s390x..."
download_and_build_arch "x86_64" "https://download.fedoraproject.org/pub/fedora/linux/releases/${MAJOR_VERSION}/Cloud/x86_64/images"
download_and_build_arch "aarch64" "https://download.fedoraproject.org/pub/fedora/linux/releases/${MAJOR_VERSION}/Cloud/aarch64/images"
download_and_build_arch "s390x" "https://download.fedoraproject.org/pub/fedora-secondary/releases/${MAJOR_VERSION}/Cloud/s390x/images"

echo "Done. Artifacts in ${OUT_DIR}:"
ls -la "${OUT_DIR}"
