# Building Fedora VM Container image

Fedora container images are now built using github actions

Fedora container images are automatically built for all 3
architectures: x86_64, aarch64, s390x when a 'pull request' issue to the
file 'containers/fedora/'

Fedora version, location and name mentioned in 'containers/fedora/fedora-vars'
is used for building fedora container images for different architectures

# Test fedora container images
When the PR is opened, Fedora container images are built and pushed to the
quay.io staging repository(quay.io/openshift-cnv/qe-cnv-tests-fedora-staging)
using the following tags:
Per-architecture: `quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<FEDORA_VERSION>-<ARCH>-pr-<PR_NUMBER>`
Multi-arch manifest: `quay.io/openshift-cnv/qe-cnv-tests-fedora-staging:<FEDORA_VERSION>-pr-<PR_NUMBER>`

Use this multi-arch image manifest for testing.
Run the required tier2 tests: smoke, network, storage, virt-compute and virt-node
to make sure that the newly built container images don't lead to any failures in
the tests. Based on those results, PR can be marked as verified.

Once the PR is merged, the container images are automatically pushed to the
production repo: `quay.io/openshift-cnv/qe-cnv-tests-fedora:<VERS>`

Once the PR is merged, the container images in the staging repo are
automatically pushed to the production repository using 
per-architecture tags:
`quay.io/openshift-cnv/qe-cnv-tests-fedora:<FEDORA_VERSION>-<ARCH>`
and also the multi-arch image manifest:
`quay.io/openshift-cnv/qe-cnv-tests-fedora:<FEDORA_VERSION>`
