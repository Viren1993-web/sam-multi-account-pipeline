FROM ubuntu:24.04 AS builder

ENV PYTHONUNBUFFERED=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
      apt-get update \
  &&  DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        git \
        curl \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        ca-certificates \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncursesw5-dev \
        xz-utils \
        tk-dev \
        libxml2-dev \
        libxmlsec1-dev \
        libffi-dev \
        liblzma-dev \
        unzip \
  &&  apt-get clean \
  &&  rm -rf /var/lib/apt/lists/*

ARG NVM_VERSION=v0.39.7
ARG PYENV_GIT_VERSION=v2.4.23
ARG PYENV_VIRTUALENV_GIT_VERSION=v1.2.4
ARG PYTHON_VERSION=3.13.1

ENV NVM_DIR=/opt/nvm
ENV PYENV_ROOT=/opt/pyenv
ENV PATH=${PYENV_ROOT}/shims:${PYENV_ROOT}/bin:${PATH}

RUN   mkdir -p ${NVM_DIR} \
  &&  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash

RUN   git clone --depth=1 --branch ${PYENV_GIT_VERSION} \
        https://github.com/pyenv/pyenv.git ${PYENV_ROOT} \
  &&  git clone --depth=1 --branch ${PYENV_VIRTUALENV_GIT_VERSION} \
        https://github.com/pyenv/pyenv-virtualenv.git ${PYENV_ROOT}/plugins/pyenv-virtualenv \
  &&  pyenv install ${PYTHON_VERSION} \
  &&  pyenv global ${PYTHON_VERSION} \
  &&  pyenv rehash

ENV PYENV_VERSION=${PYTHON_VERSION}

RUN pip install --no-cache-dir aws-sam-cli

COPY requirements.txt pyproject.toml /tmp/
COPY sam_pipeline /tmp/sam_pipeline
RUN pip install --no-cache-dir /tmp \
  &&  rm -rf /tmp/* \
  &&  find /opt/pyenv/versions -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
  &&  find /opt/pyenv/versions -type f -name "*.pyc" -delete \
  &&  find /opt/pyenv/versions -type f -name "*.pyo" -delete \
  &&  find /usr/local/lib -type f -name "*.pyc" -delete \
  &&  find /usr/local/lib -type f -name "*.pyo" -delete

# ─── Final image (minimal runtime) ─────────────────────────────────────────────
FROM ubuntu:24.04

ENV PYTHONUNBUFFERED=1

# Install ONLY runtime dependencies (no build tools)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
      apt-get update \
  &&  DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        git \
        curl \
        ca-certificates \
        libssl3 \
        zlib1g \
        libreadline8 \
        libsqlite3-0 \
        libncursesw6 \
        xz-utils \
  &&  apt-get clean \
  &&  rm -rf /var/lib/apt/lists/* /var/log/* /usr/share/doc/* /usr/share/man/*

ARG PYTHON_VERSION=3.13.1

ENV NVM_DIR=/opt/nvm
ENV PYENV_ROOT=/opt/pyenv
ENV PATH=${PYENV_ROOT}/shims:${PYENV_ROOT}/bin:${PATH}
ENV PYENV_VERSION=${PYTHON_VERSION}

COPY --from=builder /opt/nvm /opt/nvm
COPY --from=builder /opt/pyenv /opt/pyenv
COPY --from=builder /usr/local /usr/local

ARG DOCKER_IMAGE_TAG=latest
ENV APP_VERSION=${DOCKER_IMAGE_TAG}

COPY pipe.yml /opt/sam-pipeline/pipe.yml
ENV PIPE_METADATA_FILE=/opt/sam-pipeline/pipe.yml

ENTRYPOINT ["python", "-m", "sam_pipeline"]
