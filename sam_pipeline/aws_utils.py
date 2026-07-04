"""AWS utilities — STS role assumption and credential helpers."""

from __future__ import annotations

import os

import boto3

from sam_pipeline.utils import running_in_ci

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

    """
    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    if running_in_ci() and _oidc_token_available():
        response = sts.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName=ROLE_SESSION_NAME,
            WebIdentityToken=_get_oidc_token(),
            DurationSeconds=7200,
        )
    else:
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=ROLE_SESSION_NAME,
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

    resolved = credentials.resolve()
    return {
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
        "AWS_ACCOUNT_ID": account_id,
        "AWS_ACCESS_KEY_ID": resolved.access_key,
        "AWS_SECRET_ACCESS_KEY": resolved.secret_key,
        "AWS_SESSION_TOKEN": resolved.token or "",
    }


# ──────────────────────────────────────────────────────────────────────────────
# OIDC helpers
# ──────────────────────────────────────────────────────────────────────────────


def _oidc_token_available() -> bool:
    """Return True if any known OIDC token env var is set."""
    return bool(
        os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")       # GitHub Actions
        or os.environ.get("BITBUCKET_STEP_OIDC_TOKEN")       # Bitbucket Pipelines
    )


def _get_oidc_token() -> str:
    """Retrieve the OIDC token from the CI environment.

    Raises:
        EnvironmentError: When no OIDC token can be found.

    """
    # Bitbucket Pipelines — token is injected directly
    bb_token = os.environ.get("BITBUCKET_STEP_OIDC_TOKEN")
    if bb_token:
        return bb_token

    # GitHub Actions — token must be fetched via the Actions token endpoint
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if request_url and request_token:
        import urllib.request

        req = urllib.request.Request(  # noqa: S310
            f"{request_url}&audience=sts.amazonaws.com",
            headers={"Authorization": f"Bearer {request_token}"},
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            import json

            data = json.loads(resp.read())
            return str(data["value"])

    raise OSError(
        "No OIDC token found. Set BITBUCKET_STEP_OIDC_TOKEN or "
        "ACTIONS_ID_TOKEN_REQUEST_URL / ACTIONS_ID_TOKEN_REQUEST_TOKEN."
    )
