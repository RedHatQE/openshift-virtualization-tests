# Building Fedora VM Container image
Fedora container images are built using GitHub actions automatically
for all the three CPU architectures: x86_64, aarch64, s390x,
when a 'pull request' is issued to the files under the directory
'containers/fedora/'

Details about Fedora version, location and name of the fedora qcow2
file should be added to 'containers/fedora/fedora-vars' file for the
automation to build the corresponding container images.
See `containers/fedora/fedora-vars` for the expected format.

# Test fedora container images
When the PR is opened, Fedora container images are built and pushed to the
quay.io staging repository which is available at:
`quay.io/openshift-cnv/qe-cnv-tests-fedora-staging`

The stage images are available with tags containing information about the PR
and architecture with the format as follows:
`quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<FEDORA_VERSION>-<ARCH>-pr-<PR_NUMBER>`

The multi-arch manifest is available:
`quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<FEDORA_VERSION>-pr-<PR_NUMBER>`

*Where `<ARCH>` is one of: x86_64, aarch64, s390x;
`<FEDORA_VERSION>` and `<PR_NUMBER>` are sourced from fedora-vars and
the PR metadata respectively.*

# Verification
PR is marked verified when tier-2 tests (smoke, network, storage, virt-compute,
and virt-node) pass with the staged container image.

Once the PR is merged, the container images in the staging repo are
automatically pushed to the production repository using
per-architecture tags:

`quay.io/openshift-cnv/qe-cnv-tests-fedora:<FEDORA_VERSION>-<ARCH>`

The multi-arch image manifest is also created and pushed.
`quay.io/openshift-cnv/qe-cnv-tests-fedora:<FEDORA_VERSION>`
