# Building Fedora VM Container image

Fedora container images are now built using github actions

Fedora container images are automatically built for all 3
architectures: x86_64, aarch64, s390x by creating a 'pull request' to the
file 'containers/fedora/fedora-vars' by updating it with URL to download
and file name of fedora qcow2 image for all the 3 architectures....

# Test build via GitHub
To test fedora container images following steps are involved:

- Download the container images locally
- Tag images corresponding to private quay repo
- Create multi-arch image manifest
- Push the multi-arch image manifest to private quay repo
- Run tests with the new image manifest.
- Promote the images and image manifest to official repo under openshift-cnv

# 1. Download container images
- Access the action workflow on github: https://github.com/RedHatQE/openshift-virtualization-tests/actions/workflows/component-builder.yml
- Click on the relevant run
- On the bottom of the page, click on the artifact for every architecture to download.
- Once on the local storage, extract the tar file from the zip files.
```
unzip  fedora-container-image-x86_64.zip
unzip  fedora-container-image-aarch64.zip
unzip  fedora-container-image-s390x.zip
```

# 2. Tag images corresponding to private quay repo
- Load the image into the local image storage using podman
<<<<<<< HEAD
- The container images are loaded with the predefined format: 
=======
- The container images are loaded with the predefined format:
>>>>>>> 2ad0154 (OUpdated github actions workflow for ARM & s390x)
    quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<VERSION>-<ARCH>
- In this format, <VERSION> is for Fedora release version and <ARCH> is for CPU architectures: [x86_64, aarch64, s390x]
- Tag container images for each architecture with private quay repo location <REPO>.

```
podman load -i fedora-image-<FEDORA_VERSION>-x86_64.tar
podman load -i fedora-image-<FEDORA_VERSION>-aarch64.tar
podman load -i fedora-image-<FEDORA_VERSION>-s390x.tar

podman tag quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<VERSION>-x86_64 quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-x86_64
podman tag quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<VERSION>-aarch64 quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-aarch64
podman tag quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<VERSION>-s390x quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-s390x
```

# 3. Create multi-arch image manifest

- Create multi-arch image manifest using podman command
```
podman manifest create quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION> \
  quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-x86_64 \
  quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-aarch64 \
  quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-s390x \
```

# 4. Push the image manifest to private repo
- Push the container image manifest and images to the private repo
```
podman push quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-x86_64
podman push quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-aarch64
podman push quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION>-s390x
podman manifest push quay.io/<REPO>/qe-cnv-tests-fedora-staging:<VERSION> --all
```

# 5. Promotion of container images to official repo
- Make sure to run all the tier-2 tests: smoke, network, storage, virt-node and virt-compute tests.
- Once all the tests passed, contact repository owners to pull those images to advertise in public repo.
