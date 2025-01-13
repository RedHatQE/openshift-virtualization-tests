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
