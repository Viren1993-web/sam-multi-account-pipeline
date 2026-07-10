#!/usr/bin/env bash
# sam.sh
# Runs `sam build` or `sam deploy` with the correct runtime activated.

set -o errexit
set -o pipefail

source_nvm() {
  if [[ -s "${NVM_DIR}/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    source "${NVM_DIR}/nvm.sh"
  else
    echo "ERROR: NVM not found at ${NVM_DIR}/nvm.sh" >&2
    exit 43
  fi
}

sam_build() {
  local working_directory=${1:-.}
  local -a build_command=(sam build)

  echo "▶ ${build_command[*]}"
  (
    cd "${working_directory}" || { echo "ERROR: directory '${working_directory}' not found" >&2; exit 42; }
    "${build_command[@]}"
  )
}

sam_deploy() {
  local stack_name=$1
  local region=$2
  local sam_addopts=$3
  local working_directory=${4:-.}

  local -a deploy_command=(
    sam deploy
    --stack-name "${stack_name}"
    --region "${region}"
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND
    --no-confirm-changeset
    --no-fail-on-empty-changeset
    --resolve-s3
  )

  if [[ -n "${sam_addopts}" ]]; then
    local -a extra_opts=()
    read -r -a extra_opts <<<"${sam_addopts}"
    deploy_command+=("${extra_opts[@]}")
  fi

  echo "▶ ${deploy_command[*]}"
  (
    cd "${working_directory}" || { echo "ERROR: directory '${working_directory}' not found" >&2; exit 42; }
    "${deploy_command[@]}"
  )
}

main() {
  local action=$1
  local stack_name=$2
  local region=$3
  local runtime_language=$4
  local node_version=$5
  local python_version=$6
  local working_directory=${7:-.}
  local sam_addopts=${8:-}

  if [[ "${action}" != "build" && "${action}" != "deploy" ]]; then
    echo "ERROR: Invalid action '${action}'. Must be 'build' or 'deploy'." >&2
    exit 1
  fi

  source_nvm
  nvm use "${node_version}" >/dev/null

  if [[ "${runtime_language}" == "python" ]]; then
    export PYENV_VERSION="${python_version}"
  fi

  if [[ "${DEBUG:-false}" == "true" ]]; then
    echo "Node.js : $(nvm version) ($(nvm which node))"
    if [[ "${runtime_language}" == "python" ]]; then
      echo "Python  : $(pyenv version) ($(pyenv which python))"
    fi
    echo "SAM CLI : $(sam --version)"
  fi

  if [[ "${action}" == "build" ]]; then
    sam_build "${working_directory}"
  else
    sam_deploy "${stack_name}" "${region}" "${sam_addopts}" "${working_directory}"
  fi
}

main "$@"
