FROM quay.io/fedora/fedora:41 AS builder

ENV LANG=C.UTF-8
ENV ENV OPENSHIFT_VIRTUALIZATION_TESTS_CONTAINER=Yes=Yes

RUN dnf update -y \
  && dnf -y install \
  systemd-container \
  python3-devel \
  gcc \
  sshpass \
  libcurl-devel \
  libxslt-devel \
  libxml2-devel \
  which \
  && dnf clean all && rm -rf /var/cache/dnf \
  && rm -rf /var/lib/dnf \
  && truncate -s0 /var/log/*.log

COPY / /openshift-virtualization-tests/

# The following is the runner section, which we start again from a clean Fedora image
# and only adding the required bits to allow us to run the tests.
FROM quay.io/fedora/fedora:41 AS runner

ARG OPENSHIFT_VIRTUALIZATION_TESTS_DIR=/openshift-virtualization-tests

ARG OPENSHIFT_PYTHON_WRAPPER_COMMIT=''
ARG OPENSHIFT_PYTHON_UTILITIES_COMMIT=''
ARG TIMEOUT_SAMPLER_COMMIT=''

ENV LANG=C.UTF-8
ENV OPENSHIFT_VIRTUALIZATION_TESTS_CONTAINER=Yes
ENV UV_PYTHON=python3.12
ENV UV_NO_SYNC=1

WORKDIR ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}
ENV UV_CACHE_DIR=${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/.cache

##TODO: We can remove wget, and use curl instead, this will require to change some tests
RUN dnf update -y \
  && dnf install -y procps-ng python3 bind-utils jq fwknop parallel wget clang cargo rsync openssl openssl-devel git\
  && dnf clean all \
  && rm -rf /var/cache/dnf \
  && rm -rf /var/lib/dnf \
  && truncate -s0 /var/log/*.log

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/bin/
COPY --from=builder /usr/bin/which /usr/bin/which
COPY --from=builder /usr/bin/sshpass /usr/bin/sshpass
COPY --from=builder ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/ ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/

RUN uv sync --locked \
  && uv export --no-hashes \
  && if [[ -n "${OPENSHIFT_PYTHON_WRAPPER_COMMIT}" ]]; then uv pip install git+https://github.com/RedHatQE/openshift-python-wrapper.git@$OPENSHIFT_PYTHON_WRAPPER_COMMIT; fi \
  && if [[ -n "${OPENSHIFT_PYTHON_UTILITIES_COMMIT}" ]]; then uv pip install git+https://github.com/RedHatQE/openshift-python-utilities.git@$OPENSHIFT_PYTHON_UTILITIES_COMMIT; fi \
  && if [[ -n "${TIMEOUT_SAMPLER_COMMIT}" ]]; then uv pip install git+https://github.com/RedHatQE/timeout-sampler.git@$TIMEOUT_SAMPLER_COMMIT; fi \
  && rm -rf ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/.cache \
  && rm -rf ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/artifacts \
  && find ${OPENSHIFT_VIRTUALIZATION_TESTS_DIR}/ -type d -name "__pycache__" -print0 | xargs -0 rm -rfv

CMD ["uv", "run", "pytest", "--tc=server_url:${HTTP_IMAGE_SERVER}", "--collect-only"]
