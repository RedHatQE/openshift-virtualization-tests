# Building Fedora VM Container image

Fedora container images are now built using github actions

Fedora container images are automatically built for all 3
architectures: x86_64, aarch64, s390x when a 'pull request' issue to the
file 'containers/fedora/'

Fedora version, location and name mentioned in 'containers/fedora/fedora-vars'
is used for building fedora container images for different architectures

# Test fedora container images
When the PR is issued, fedora container images are built and pushed to
quay.io repository: quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<VERS>-<PR>

Use this multi-arch image manifest for testing.
Run the required tier2 tests: smoke, network, storage, virt-compute and virt-node
for marking the PR as verified.

Once the PR is merged, the container images are automatically available in the
production repo: quay.io/openshift-cnv/qe-cnv-tests-fedora:<VERS>
