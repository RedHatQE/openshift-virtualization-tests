IMAGE_BUILD_CMD = "$(shell which podman 2>/dev/null || which docker)"
IMAGE_REGISTRY ?= "quay.io"
ORG_NAME ?= "openshift-cnv"
IMAGE_NAME ?= "openshift-virtualization-tests"
IMAGE_TAG ?= "latest"

FULL_OPERATOR_IMAGE ?= "$(IMAGE_REGISTRY)/$(ORG_NAME)/$(IMAGE_NAME):$(IMAGE_TAG)"

all: check poetry run_cluster_sanity_tests build-container push-container
publish-image: build-container push-container

check:
	tox

poetry:
	-poetry env remove --all
	poetry install
	poetry show

build-container:
	$(IMAGE_BUILD_CMD) build --no-cache -f Dockerfile -t $(FULL_OPERATOR_IMAGE) .

push-container:
	$(IMAGE_BUILD_CMD) push $(FULL_OPERATOR_IMAGE)

.PHONY: all
