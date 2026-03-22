# Fedora base disk artifacts for Artifactory

This directory builds **base** (official) Fedora cloud disk images in all formats used by tests: qcow2, raw, qcow2.gz, qcow2.xz, raw.gz, raw.xz. Output is written to `out/` for upload to Artifactory.

The **customized** qcow2 (sysprepped, with stress-ng etc.) is produced by [containers/fedora/build.sh](../fedora/build.sh) and is separate; see optional step below to collect everything in one place.

## Requirements

- `wget`, `qemu-img`, `gzip`, `xz`

Install commands:

**macOS (ARM64):**
```bash
brew install wget qemu gzip xz
```
(`qemu-img` is provided by the `qemu` package.)

**Linux (amd64):**
```bash
# Debian / Ubuntu
sudo apt-get update && sudo apt-get install -y wget qemu-utils gzip xz-utils

# RHEL / Fedora
sudo dnf install -y wget qemu-img gzip xz
```

## Usage

```bash
# From repo root or from this directory
FEDORA_VERSION=41-1.4 ./containers/fedora_artifacts/build.sh

# Or pass version as first argument
./containers/fedora_artifacts/build.sh 43-1.6
```

Builds for **x86_64**, **aarch64**, and **s390x**. Artifacts are placed in `containers/fedora_artifacts/out/`. Allow **30 minutes or more** for a full run (downloads and compression).

## Output layout (per arch)

For each architecture the script produces:

- `Fedora-Cloud-Base-Generic-<version>.<arch>.qcow2` → renamed to **`Fedora-qcow2-<arch>.img`**
- `Fedora-Cloud-Base-Generic-<version>.<arch>.qcow2.gz`
- `Fedora-Cloud-Base-Generic-<version>.<arch>.qcow2.xz`
- `Fedora-Cloud-Base-Generic-<version>.<arch>.raw`
- `Fedora-Cloud-Base-Generic-<version>.<arch>.raw.gz`
- `Fedora-Cloud-Base-Generic-<version>.<arch>.raw.xz`

## Optional: use customized qcow2 in `out/`

If you have already built the **customized** Fedora image with `containers/fedora/build.sh` for an arch, you can copy it into `out/` so all artifacts to upload to Artifactory are in one place.

Example for s390x (after running `containers/fedora/build.sh` with s390x):

```bash
cp containers/fedora/fedora_build_s390x/Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2 \
   containers/fedora_artifacts/out/
```

Then upload the contents of `containers/fedora_artifacts/out/` to Artifactory.

## Upload to Artifactory (JFrog CLI)

**Install (macOS):**
```bash
brew install jfrog-cli
```
Other platforms: [JFrog CLI](https://jfrog.com/getcli/) (`jf`).

**1. Log in:**
```bash
jf login
```
- Enter your JFrog Platform URL: `https://cnv-qe-artifactory.<...>.redhat.com/`
- Enter "save and continue"
- Authenticate in the browser when prompted

**2. Upload artifacts from `out/`:**
```bash
cd containers/fedora_artifacts/out

# Upload all s390x artifacts
jf rt upload "*s390x*" cnv-qe-server-local/cnv-tests/fedora-images/
```

**Caution:** Before uploading all architectures, ensure you are selecting the right files (e.g. by arch or version) so you do not overwrite existing artifacts in Artifactory.

```bash
# Upload all architectures (x86_64, aarch64, s390x)
jf rt upload "*" cnv-qe-server-local/cnv-tests/fedora-images/
```
