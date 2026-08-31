# Fedora VM and Container Image Build Script

This script automates the preparation of a Fedora virtual machine (VM) image, customizes it with `cloud-init`,
and packages it into a container image.
The final container image is saved as a tarball for further use.

## Prerequisites

### Software Requirements
Ensure the following tools are installed on your system:
- `podman` or `docker`
- `virt-install`
- `virsh`
- `qemu-img`
- `cloud-localds`
- `virt-sysprep`
- `qemu-efi-aarch64` / `AAVMF` (required for `arm64` UEFI vars)
- `qemu-system-aarch64` (required for local `arm64` builds)
- `qemu-system-s390x` (required for local `s390x` builds)
- `libguestfs-tools` (provides `guestfish` and `virt-sysprep`, required for `arm64` BLS kernel cmdline patching and image sysprep)

Ensure Your Python Environment Is Ready
Install the required Python dependencies: Run the following command to set up the Python environment:
```bash
uv sync
```

### Environment Variables
Set the following environment variables before running the script:
- `FEDORA_IMAGE`: Path to the Fedora base image file (e.g., `Fedora-Cloud-Base-Generic.43-1.6.x86_64.qcow2`).
- `FEDORA_VERSION`: Version of Fedora (e.g., `43`).
- `CPU_ARCH`: Target CPU architecture. Use `amd64` for x86_64, `arm64` for aarch64, or `s390x` for s390x.
- `ACCESS_TOKEN`: Bitwarden access token for authentication.
- `ORGANIZATION_ID`: Bitwarden organization ID for accessing secrets.

### Permissions
Ensure you have the necessary permissions to run virtualization and container-related tools.

## How to Use

### Step 1: Set Required Environment Variables
Define the environment variables in your shell:
```bash
export FEDORA_IMAGE=/path/to/fedora-image.qcow2
export FEDORA_VERSION=43
export CPU_ARCH=amd64  # Use arm64 or s390x if targeting ARM or s390x architecture
```

### Step 2: Ensure You Are Logged In to quay.io
```bash
podman login quay.io
```

### Step 3: Run the Script
Execute the script in a terminal:
```bash
./build.sh
```

### Step 4: Script Workflow
1. Validates the required environment variables.
2. Determines appropriate virtualization settings based on CPU_ARCH.
3. Creates a working directory named `fedora_build_${CPU_ARCH}`.
4. Generates a secure password for the VM OS login.
5. Configures cloud-init with the secure password.
6. Runs the Fedora VM and performs customizations.
7. Converts the final VM image to a compressed qcow2 format.
8. Creates a Dockerfile to package the image into a container.
9. Builds the container image and saves it as a tarball.

### Step 5: Retrieve Outputs
The resulting files are stored in the `fedora_build_${CPU_ARCH}` directory:
1. Compressed VM Image: A compressed .qcow2 file.
2. Dockerfile: Used to build the container image.
3. Container Image Tarball.

### Step 6: Creating multi-arch image manifest

> **⚠️ Only follow this step for local/manual builds.**
> When a PR that touches `containers/fedora/**` or `.github/component-builder-config.json`
> is merged to `main`, CI automatically handles everything up to and including the
> staging multi-arch manifest (see [CI pipeline](#ci-pipeline-automated) below).
> Skip to [Staging → production promotion](#staging--production-promotion-manual) instead.

After building VM images for Fedora AMD64, ARM64, and S390X architectures, the
following procedure should help in building multi-arch image manifest

1. Create a new tag for container images with revision number.

Note: Revision number is required to prevent overriding of existing tags
in the container image 'qe-cnv-tests-fedora'. Revision number is not
required for the very first build of Fedora container image. Revision
number is created with naming convention as *.rev-YYMMDD* suffixed to
the image tag.

Make sure that the chosen tag does not exist already for the fedora
container image
```bash
export REV=.rev-250317
oc image info quay.io/openshift-cnv/qe-cnv-tests-fedora:43${REV}
oc image info quay.io/openshift-cnv/qe-cnv-tests-fedora:43-amd64${REV}
oc image info quay.io/openshift-cnv/qe-cnv-tests-fedora:43-arm64${REV}
oc image info quay.io/openshift-cnv/qe-cnv-tests-fedora:43-s390x${REV}
```
Above commands should return 'image not found'. After confirming that these
tags are not used already, they can be used to tag images

```bash
podman tag localhost/fedora:43-amd64 quay.io/openshift-cnv/qe-cnv-tests-fedora:43-amd64${REV}
podman tag localhost/fedora:43-arm64 quay.io/openshift-cnv/qe-cnv-tests-fedora:43-arm64${REV}
podman tag localhost/fedora:43-s390x quay.io/openshift-cnv/qe-cnv-tests-fedora:43-s390x${REV}
```

2. Create a new multi-arch image manifest with the images
```bash
podman manifest create quay.io/openshift-cnv/qe-cnv-tests-fedora:43${REV} \
  quay.io/openshift-cnv/qe-cnv-tests-fedora:43-amd64${REV} \
  quay.io/openshift-cnv/qe-cnv-tests-fedora:43-arm64${REV} \
  quay.io/openshift-cnv/qe-cnv-tests-fedora:43-s390x${REV}
```

3. Inspect the multi-arch image manifest
```bash
podman manifest inspect quay.io/openshift-cnv/qe-cnv-tests-fedora:43${REV} | jq '.manifests[]|."platform"|."architecture"'
```
The above should list *amd64*, *arm64*, and *s390x* as output, which means that architecture-specific images are now part of the image
manifest

4. Push the images and multi-arch image manifest
```bash
podman push quay.io/openshift-cnv/qe-cnv-tests-fedora:43-amd64${REV}
podman push quay.io/openshift-cnv/qe-cnv-tests-fedora:43-arm64${REV}
podman push quay.io/openshift-cnv/qe-cnv-tests-fedora:43-s390x${REV}
podman manifest push quay.io/openshift-cnv/qe-cnv-tests-fedora:43${REV} --all --format=v2s2
```

5. Swapping newly built image for latest

This step is required only if fedora container image is rebuilt for the
existing fedora container image.

Once the new multi-arch image is validated, this should be swapped for the
current active tag. This can be done by creating a new tag for current 'active'
tag and then creating a new tag same as 'active' tag for the newly pushed
multi-arch image manifest.

This operation is performed from quay.io web UI.

For example, if the latest tag for 'qe-cnv-tests-fedora' is '43'
and new multi-arch image is validated with tag '43.rev-250318'.

Check if there is an existing 'rev-xxxxxx' tag associated with the active tag (i.e) 43.
In this case, new tag for uploaded multi-arch image manifest can be created same
as active tag (i.e) 43
Otherwise:
a. New tag is created for the active tag '43' as '43.rev-xxxxxx'
b. then new tag for uploaded multi-arch image manifest '43.rev-250318' is created as '43'.

This way there will be minimal impact for test runs that
tried to pull the latest fedora container image with tag '43'

## CI Pipeline (automated)

Merging any change to `containers/fedora/**`, `.github/component-builder-config.json`,
or either of the shared workflow files (`component-builder-prepare.yml`,
`component-builder-build.yml`) into `main` automatically triggers
[`component-builder-publish.yml`](../../.github/workflows/component-builder-publish.yml).

**You do not need to run any of the steps above after a PR merge — CI does this for you.**

The automated pipeline performs the following steps in sequence:

1. **Read config** — reads `FEDORA_VERSION` and the architecture matrix from
   `.github/component-builder-config.json`.
2. **Build all architectures in parallel** — for each arch (`amd64`, `arm64`, `s390x`):
   - Downloads and SHA-256 verifies the upstream Fedora cloud image.
   - Builds the VM and packages it into a container image.
   - Pushes the per-arch image as
     `quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:${FEDORA_VERSION}-${arch}`
     (e.g. `…:43-amd64`).
3. **Create and push multi-arch manifest** — assembles all per-arch images into a
   single multi-arch manifest and pushes it as
   `quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:${FEDORA_VERSION}-dev`
   (e.g. `…:43-dev`).

The pipeline uses the `QUAY_USER` / `QUAY_TOKEN` GitHub secrets; no manual
registry login is required.

> **Note:** The `component-builder.yml` workflow also runs on every **pull request**
> that touches the same paths.  On PRs it builds all architectures but does **not**
> push to any registry; it uploads the images as downloadable workflow artifacts
> instead (see [Test build via GitHub](#test-build-via-github) below).

## Component Builder Configuration

All multi-arch build options, Fedora image versions, checksums, and target architecture matrices are central to `.github/component-builder-config.json`.
To update the Fedora version or target CPU architectures, update this configuration file ("one-file-edit" workflow):

```json
{
  "fedora_version": "43",
  "fedora_image_base": "Fedora-Cloud-Base-Generic-43-1.6",
  "fedora_checksum_base": "Fedora-Cloud-43-1.6",
  "remote_repository": "quay.io/openshift-cnv/qe-cnv-tests-fedora-staging",
  "matrix": {
    "include": [
      {
        "arch": "amd64",
        "url_arch": "x86_64",
        "qemu_package": "qemu-system-x86",
        "fedora_url": "https://download.fedoraproject.org/pub/fedora/linux/releases/43/Cloud/x86_64/images"
      },
      ...
    ]
  }
}
```

| Key | Description |
|---|---|
| `fedora_version` | Fedora major version number (e.g. `"43"`) |
| `fedora_image_base` | Base filename of the Fedora Cloud image (without architecture suffix and extension) |
| `fedora_checksum_base` | Base filename of the Fedora checksum file (without architecture suffix) |
| `remote_repository` | Target container registry repository for tagging and pushing images (e.g. `quay.io/org/repo`) |
| `matrix.include` | Per-architecture build parameters (`arch`, `url_arch`, `qemu_package`, `fedora_url`) |

Editing `.github/component-builder-config.json` automatically updates the GitHub workflow parameters and matrix for builds, tests, and releases across all specified architectures (`amd64`, `arm64`, `s390x`).

# Test build via GitHub
When pushing a new commit which affects a file under this directory or `.github/component-builder-config.json`, a GitHub action will be triggered to build new Fedora container images.
To test these images locally:
- Access the action workflow on GitHub: https://github.com/RedHatQE/openshift-virtualization-tests/actions/workflows/component-builder.yml
- Click on the relevant run
- At the bottom of the page, click on the architecture-specific artifact to download (`fedora-container-image-amd64`, `fedora-container-image-arm64`, or `fedora-container-image-s390x`).
- Once on local storage, extract the tar file from the zip archive.
- Load the image into local image storage using podman:
```bash
podman load -i fedora-image-${CPU_ARCH}.tar
```
For example, for `amd64`:
```bash
podman load -i fedora-image-amd64.tar
```
