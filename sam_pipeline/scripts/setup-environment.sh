#!/usr/bin/env bash
# setup-environment.sh
# Installs the correct Node.js and Python versions inside the container.

set -o errexit
set -o pipefail

source_nvm() {
  if [[ -s "${NVM_DIR}/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    source "${NVM_DIR}/nvm.sh"
  else
    echo "ERROR: NVM not found at ${NVM_DIR}/nvm.sh" >&2
    exit 3
  fi
}

setup_environment() {
  local runtime_language=$1
  local node_version=$2
  local python_version=$3

  echo "Installing Node.js ${node_version} ..."
  nvm install "${node_version}"

  if [[ "${runtime_language}" == "python" ]]; then
    echo "Installing Python ${python_version} ..."
    pyenv install "${python_version}" --skip-existing
  fi
}

source_nvm
setup_environment "$@"
