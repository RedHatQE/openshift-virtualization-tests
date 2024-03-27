FROM fedora:39

ARG OPENSHIFT_PYTHON_WRAPPER_COMMIT=''
ARG POETRY_HOME='/usr/local'

RUN dnf install --nodocs -y --setopt=install_weak_deps=False dnf-plugins-core && \
    dnf config-manager --add-repo https://rpm.releases.hashicorp.com/fedora/hashicorp.repo && \
    dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && \
    dnf install --nodocs -y --setopt=install_weak_deps=False --setopt=skip_missing_names_on_install=False \
    python3-pip \
    python3-devel \
    procps-ng \
    rsync \
    gcc \
    git \
    libcurl-devel \
    libxslt-devel \
    libxml2-devel \
    openssl-devel \
    terraform \
    vim \
    gh && \
    dnf clean all && \
    rm -rf /var/cache/yum

ENV USER_HOME=/home/openshift-virtualization-tests
ENV PATH="${PATH}:$USER_HOME/.local/bin"

COPY . /openshift-virtualization-tests/
WORKDIR /openshift-virtualization-tests/

RUN python3 -m pip install pip --upgrade \
    && python3 -m venv ${POETRY_HOME} \
    && ${POETRY_HOME}/bin/pip install pip --upgrade \
    && ${POETRY_HOME}/bin/pip install poetry \
    && ${POETRY_HOME}/bin/poetry --version \
    && ${POETRY_HOME}/bin/poetry config cache-dir /openshift-virtualization-tests \
    && ${POETRY_HOME}/bin/poetry config virtualenvs.in-project true \
    && ${POETRY_HOME}/bin/poetry config --list \
    && ${POETRY_HOME}/bin/poetry install \
    && ${POETRY_HOME}/bin/poetry export --without-hashes -n \
    && if [[ -n "${OPENSHIFT_PYTHON_WRAPPER_COMMIT}" ]];   then ${POETRY_HOME}/bin/poetry run pip install git+https://github.com/RedHatQE/openshift-python-wrapper.git@$OPENSHIFT_PYTHON_WRAPPER_COMMIT -U; fi \
    && rm -rf /openshift-virtualization-tests/cache \
    && rm -rf /openshift-virtualization-tests/artifacts \
    && find /openshift-virtualization-tests/  -type d -name "__pycache__" -print0 | xargs -0 rm -rfv

ENV OPENSHIFT_PYTHON_WRAPPER_LOG_LEVEL=DEBUG

ENTRYPOINT ["poetry", "run", "pytest"]
CMD ["--collect-only"]
