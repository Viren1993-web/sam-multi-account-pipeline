"""Utility helpers for the SAM pipeline."""

from __future__ import annotations

import os
import subprocess
import sys

from sam_pipeline.exceptions import SubprocessError


def run_command(
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command, streaming output to stdout/stderr.

    Args:
        *args: Command and its arguments.
        env: Environment variables for the subprocess.
        check: If True, raise SubprocessError on non-zero exit.

    Returns:
        CompletedProcess instance.

    Raises:
        SubprocessError: When the command exits with a non-zero code and check=True.

    """
    command_str = " ".join(args)
    result = subprocess.run(  # noqa: S603
        list(args),
        env=env,
        text=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if check and result.returncode != 0:
        raise SubprocessError(returncode=result.returncode, command=command_str)
    return result


def running_in_ci() -> bool:
    """Return True when the process is running inside a CI environment."""
    return os.environ.get("CI", "").lower() == "true"


def get_repo_name() -> str:
    """Return the repository name from common CI environment variables.

    Falls back to the current working directory name.
    """
    # GitHub Actions
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        return repo.split("/")[-1]

    # Bitbucket Pipelines
    slug = os.environ.get("BITBUCKET_REPO_SLUG", "")
    if slug:
        return slug

    return os.path.basename(os.getcwd())


def bool_from_env(value: str | bool | None) -> bool:
    """Convert an environment variable string to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return False
