"""AWS utilities — STS role assumption and credential helpers."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, cast

import boto3

from sam_pipeline.utils import running_in_ci

logger = logging.getLogger(__name__)

ROLE_SESSION_NAME = "sam-pipeline"


def assume_role_session(
    account_id: str,
    region: str,
    role_name: str = "DeployerAccess",
) -> boto3.Session:
    """Assume an IAM role in a target account and return a boto3 Session.

    In CI the role is assumed via OIDC (web identity token). Locally it uses
    standard STS AssumeRole so engineers can test against sandbox accounts.

    Args:
        account_id: AWS account ID of the target account.
        region: AWS region to target.
        role_name: IAM role name to assume in the target account.

    Returns:
        An authenticated boto3.Session scoped to the target account.

    Raises:
        ValueError: When account_id or role_name are empty/None.

    """
    if not account_id or not account_id.strip():
        raise ValueError("account_id is required and cannot be empty")
    if not role_name or not role_name.strip():
        raise ValueError("role_name is required and cannot be empty")

    account_id = account_id.strip()
    role_name = role_name.strip()

    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    if running_in_ci() and _oidc_token_available():
        try:
            token = _get_oidc_token()
        except OSError as exc:
            raise ValueError(
                "Failed to retrieve OIDC token in CI environment. "
                "Ensure ACTIONS_ID_TOKEN_REQUEST_URL and "
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN are set (GitHub Actions) "
                "or BITBUCKET_STEP_OIDC_TOKEN (Bitbucket Pipelines).",
            ) from exc

        response = cast(
            "dict[str, Any]",
            sts.assume_role_with_web_identity(
                RoleArn=role_arn,
                RoleSessionName=ROLE_SESSION_NAME,
                WebIdentityToken=token,
                DurationSeconds=1800,  # 30 minutes — sufficient for any SAM build+deploy
            ),
        )
    else:
        response = cast(
            "dict[str, Any]",
            sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=ROLE_SESSION_NAME,
            ),
        )

    credentials = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=region,
    )


def session_to_env(session: boto3.Session, region: str, account_id: str) -> dict[str, str]:
    """Extract AWS credentials from a session into a dict of environment variables.

    Args:
        session: An authenticated boto3.Session.
        region: AWS region.
        account_id: AWS account ID.

    Returns:
        Dict mapping environment variable names to their values.

    """
    credentials = session.get_credentials()
    if credentials is None:
        raise ValueError("Failed to retrieve credentials from the boto3 session")

    frozen = credentials.get_frozen_credentials()
    return {
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
        "AWS_ACCOUNT_ID": account_id,
        "AWS_ACCESS_KEY_ID": cast("str", frozen.access_key),
        "AWS_SECRET_ACCESS_KEY": cast("str", frozen.secret_key),
        "AWS_SESSION_TOKEN": frozen.token or "",
    }


# ──────────────────────────────────────────────────────────────────────────────
# OIDC helpers
# ──────────────────────────────────────────────────────────────────────────────


def _oidc_token_available() -> bool:
    """Return True if any known OIDC token env var is set."""
    return bool(
        os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")  # GitHub Actions
        or os.environ.get("BITBUCKET_STEP_OIDC_TOKEN"),  # Bitbucket Pipelines
    )


def _get_oidc_token() -> str:
    """Retrieve the OIDC token from the CI environment.

    Raises:
        EnvironmentError: When no OIDC token can be found or fetched.

    """
    # Bitbucket Pipelines — token is injected directly
    bb_token = os.environ.get("BITBUCKET_STEP_OIDC_TOKEN")
    if bb_token:
        logger.debug("Using Bitbucket Pipelines OIDC token")
        return bb_token

    # GitHub Actions — token must be fetched via the Actions token endpoint
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")

    if not request_url:
        raise OSError(
            "ACTIONS_ID_TOKEN_REQUEST_URL not set. "
            "Ensure the job has `permissions: { id-token: write }` "
            "and runs in GitHub Actions.",
        )

    if not request_token:
        raise OSError(
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN not set. "
            "This should be automatically set by GitHub Actions.",
        )

    try:
        logger.debug(
            "Fetching OIDC token from GitHub Actions token endpoint",
        )
        req = urllib.request.Request(  # noqa: S310
            f"{request_url}&audience=sts.amazonaws.com",
            headers={"Authorization": f"Bearer {request_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
            logger.debug("Successfully retrieved OIDC token from GitHub Actions")
            return str(data["value"])
    except urllib.error.HTTPError as exc:
        logger.exception(
            "HTTP error when fetching OIDC token: %s %s",
            exc.code,
            exc.reason,
        )
        raise OSError(
            f"HTTP {exc.code} when fetching OIDC token from GitHub Actions. Reason: {exc.reason}",
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        logger.exception("Failed to fetch OIDC token from GitHub Actions")
        raise OSError(
            "Failed to fetch OIDC token from GitHub Actions. "
            "Ensure ACTIONS_ID_TOKEN_REQUEST_URL is accessible "
            "from the container. "
            f"Error: {exc}",
        ) from exc
