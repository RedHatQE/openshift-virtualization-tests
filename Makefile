# Pytest args handling
PYTEST_ARGS ?= tests --tc-file=tests/global_config.py --tc-format=python

#OPENSHIFT_PYTHON_WRAPPER LOG LEVEL
export OPENSHIFT_PYTHON_WRAPPER_LOG_LEVEL=DEBUG


# Building openshift-virtualization-tests container for disconnected clusters
IMAGE_BUILD_CMD = $(shell which podman 2>/dev/null || which docker)
IMAGE_REGISTRY ?= "quay.io"
REGISTRY_NAMESPACE ?= "openshift-cnv"
OPERATOR_IMAGE_NAME="openshift-virtualization-tests-github"
# Need to change when main point to new version of openshift-virtualization-tests
IMAGE_TAG ?= "latest"

FULL_OPERATOR_IMAGE ?= "$(IMAGE_REGISTRY)/$(REGISTRY_NAMESPACE)/$(OPERATOR_IMAGE_NAME):$(IMAGE_TAG)"
UV_BIN = uv

all: check

check:
	tox

venv-install:
	$(UV_BIN) sync

build-container:
	$(IMAGE_BUILD_CMD) build --network=host --no-cache -f Dockerfile -t $(FULL_OPERATOR_IMAGE) --build-arg OPENSHIFT_PYTHON_WRAPPER_COMMIT=$(OPENSHIFT_PYTHON_WRAPPER_COMMIT) --build-arg OPENSHIFT_PYTHON_UTILITIES_COMMIT=$(OPENSHIFT_PYTHON_UTILITIES_COMMIT) --build-arg TIMEOUT_SAMPLER_COMMIT=$(TIMEOUT_SAMPLER_COMMIT) .

push-container:
	$(IMAGE_BUILD_CMD) push $(FULL_OPERATOR_IMAGE)

build-and-push-container: build-container push-container

.PHONY: \
	check \
	build-container \
	push-container \
	build-and-push-container \
