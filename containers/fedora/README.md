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

Ensure Your Python Environment Is Ready
Install the required Python dependencies: Run the following command to set up the Python environment:
```bash
uv sync
```

### Environment Variables
Set the following environment variables before running the script:
- `FEDORA_IMAGE`: Path to the Fedora base image file (e.g., `Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2`).
- `FEDORA_VERSION`: Version of Fedora (e.g., `40`).
- `CPU_ARCH`: Target CPU architecture. Use `amd64` for x86_64 or `arm64` for aarch64.
- `ACCESS_TOKEN`: Bitwarden access token for authentication.
- `ORGANIZATION_ID`: Bitwarden organization ID for accessing secrets.

### Permissions
Ensure you have the necessary permissions to run virtualization and container-related tools.

## How to Use

### Step 1: Set Required Environment Variables
Define the environment variables in your shell:
```bash
export FEDORA_IMAGE=/path/to/fedora-image.qcow2
export FEDORA_VERSION=40
export CPU_ARCH=amd64  # Use arm64 if targeting ARM architecture
```

### Step 2: Ensure You Are Logged In to quay.io
```bash
podman login quay.io
```

### Step 3: Run the Script
Execute the script in a terminal:
```bash
./build-fedora-vm.sh
```

### Step 4: Script Workflow
1. Validates the required environment variables.
2. Determines appropriate virtualization settings based on CPU_ARCH.
3. Creates a working directory named fedora_build.
4. Generates a secure password for the VM OS login.
5. Configures cloud-init with the secure password.
6. Runs the Fedora VM and performs customizations.
7. Converts the final VM image to a compressed qcow2 format.
8. Creates a Dockerfile to package the image into a container.
9. Builds the container image and saves it as a tarball.

### Step 5: Retrieve Outputs
The resulting files are stored in the fedora_build directory:
1. Compressed VM Image: A compressed .qcow2 file.
2. Dockerfile: Used to build the container image.
3. Container Image Tarball.

### Step 6: Creating multi-arch image manifest
After building VM images for Fedora AMD64 and ARM64 architectures,the
following procedure should help in building multi-arch image manifest

1. Create a new tag for container images with revision number.

Note: Revision number is required to prevent override of existing tags
in the container image 'quay.io/openshift-cnv/qe-cnv-tests-fedora'.
Revision number is optional for the very first build of Fedora container
image. Revision number is created with naming
convention as *.rev-YYMMDD* suffixed to the image tag.

```bash
podman tag localhost/fedora:41-amd64 quay.io/openshift-cnv/qe-cnv-tests-fedora:41-amd64[.rev-250316]
podman tag localhost/fedora:41-arm64 quay.io/openshift-cnv/qe-cnv-tests-fedora:41-arm64[.rev-250316]
```

2. Create a new multi-arch image manifest with the images
```bash
podman manifest create quay.io/openshift-cnv/qe-cnv-tests-fedora:41[.rev-250316] \
  quay.io/openshift-cnv/qe-cnv-tests-fedora:41-amd64[.rev-250316] \
  quay.io/openshift-cnv/qe-cnv-tests-fedora:41-arm64[.rev-250316]
```

3. Inspect the multi-arch image manifest
```bash
podman manifest inspect quay.io/openshift-cnv/qe-cnv-tests-fedora:41[.rev-250317] | jq '.manifests[]|."platform"|."architecture"'
```
The above should list *amd64* and *arm64* as output, which means that architecture specific images are now part of image
manifest

4. Push the images and multi-arch image manifest
```bash
podman push quay.io/openshift-cnv/qe-cnv-tests-fedora:41-amd64[.rev-250317]
podman push quay.io/openshift-cnv/qe-cnv-tests-fedora:41-arm64[.rev-250317]
podman manifest push quay.io/openshift-cnv/qe-cnv-tests-fedora:41[.rev-250317] --all --format=v2s2
```

5. Update quay.io

Once the new multi-arch image is validated, current latest tag for 'qe-cnv-tests-fedora'
is archived and then new latest tag is made to point to the new multi-arch image manifest.
This is performed from quay.io web UI.

For example, if the latest tag for 'qe-cnv-tests-fedora' is '41'
and new multi-arch image is validated with tag '41.rev-250318'.

Now new tag is created for existing '41' as '41.prev', then new tag for '41.rev-250318' is
created as '41'. This way there will be very minimal impact for test runs that
tried to pull the latest fedora container image with tag '41'

