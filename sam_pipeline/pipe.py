"""Main pipeline orchestration."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

import cerberus

from sam_pipeline.accounts import AccountTarget, parse_account_ids
from sam_pipeline.aws_utils import assume_role_session, session_to_env
from sam_pipeline.exceptions import (
    NvmNotFoundError,
    SamBuildError,
    SamDeployError,
    SubprocessError,
    ValidationError,
    WorkingDirectoryNotFoundError,
)
from sam_pipeline.schema import schema
from sam_pipeline.utils import bool_from_env, get_repo_name, run_command

logger = logging.getLogger(__name__)

# Exit codes returned by sam.sh
_EXIT_WORKING_DIR_NOT_FOUND = 2
_EXIT_NVM_NOT_FOUND = 3


class SamPipeline:
    """Orchestrates multi-account AWS SAM deployments."""

    def __init__(self) -> None:
        self._scripts_dir: Path = Path(__file__).parent / "scripts"
        self._vars: dict[str, Any] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Read inputs, validate, then deploy to all configured accounts."""
        self._configure_logging()
        self._vars = self._load_and_validate()

        logger.info("SAM Multi-Account Pipeline starting")
        self._log_variables()

        accounts = self._resolve_accounts()
        logger.info("Deploying to %d account(s)", len(accounts))

        self._setup_environment()

        failed: list[AccountTarget] = []
        for target in accounts:
            try:
                self._deploy(target)
            except (SamBuildError, SamDeployError) as exc:
                logger.error("Deployment failed: %s", exc)  # noqa: TRY400
                failed.append(target)

        if failed:
            ids = ", ".join(t.account_id for t in failed)
            logger.error("Pipeline finished with failures in account(s): %s", ids)
            sys.exit(1)

        logger.info("Pipeline finished successfully")

    # ──────────────────────────────────────────────────────────────────────────
    # Variable helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_and_validate(self) -> dict[str, Any]:
        """Read env vars, apply defaults and validate against the schema."""
        raw: dict[str, Any] = {}
        for key in schema:
            val = os.environ.get(key)
            if val is not None:
                raw[key] = val

        validator = cerberus.Validator(schema, allow_unknown=True)
        if not validator.validate(raw):
            raise ValidationError(validator.errors)

        return validator.document  # type: ignore[no-any-return]

    def _get(self, key: str) -> str | None:
        return self._vars.get(key)

    def _configure_logging(self) -> None:
        debug = bool_from_env(os.environ.get("DEBUG", "false"))
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(levelname)s │ %(message)s",
            stream=sys.stdout,
        )

    def _log_variables(self) -> None:
        sensitive = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
        lines = [f"  {k}: {'***' if k in sensitive else v}" for k, v in sorted(self._vars.items())]
        logger.info("Configuration:\n%s", "\n".join(lines))

    # ──────────────────────────────────────────────────────────────────────────
    # Account resolution
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_accounts(self) -> list[AccountTarget]:
        """Return the list of target accounts from env vars."""
        default_region: str = self._get("AWS_REGION") or "us-east-1"

        raw_ids = os.environ.get("AWS_ACCOUNT_IDS", "").strip()
        if raw_ids:
            return parse_account_ids(raw_ids, default_region)

        account_id = os.environ.get("AWS_ACCOUNT_ID", "").strip()
        if account_id:
            return [AccountTarget(account_id=account_id, region=default_region)]

        raise ValueError(
            "No target accounts configured. "
            "Set AWS_ACCOUNT_ID or AWS_ACCOUNT_IDS environment variable.",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Environment setup
    # ──────────────────────────────────────────────────────────────────────────

    def _setup_environment(self) -> None:
        """Install the correct Node / Python versions inside the container."""
        logger.info("Setting up runtime environment")
        script = (self._scripts_dir / "setup-environment.sh").as_posix()
        run_command(
            script,
            cast("str", self._get("RUNTIME_LANGUAGE")),
            cast("str", self._get("NODE_VERSION")),
            cast("str", self._get("PYTHON_VERSION")),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Deployment
    # ──────────────────────────────────────────────────────────────────────────

    def _deploy(self, target: AccountTarget) -> None:
        """Assume the deployer role, then build and deploy SAM to ``target``."""
        logger.info("Assuming role in account %s (%s)", target.account_id, target.region)

        role_name: str = self._get("DEPLOYER_ROLE_NAME") or "DeployerAccess"
        session = assume_role_session(
            account_id=target.account_id,
            region=target.region,
            role_name=role_name,
        )

        cred_env = session_to_env(session, target.region, target.account_id)
        env = (
            os.environ.copy()
            | cred_env
            | {
                "DEBUG": "true" if bool_from_env(self._get("DEBUG")) else "false",
            }
        )

        stack_name = self._resolve_stack_name()
        logger.info("Deploying stack '%s' to %s", stack_name, target.account_id)

        self._run_sam("build", stack_name, target.region, env, target.account_id)
        self._run_sam("deploy", stack_name, target.region, env, target.account_id)

        logger.info("Successfully deployed to account %s", target.account_id)

    def _run_sam(
        self,
        action: str,
        stack_name: str,
        region: str,
        env: dict[str, str],
        account_id: str,
    ) -> None:
        script = (self._scripts_dir / "sam.sh").as_posix()
        try:
            run_command(
                script,
                action,
                stack_name,
                region,
                cast("str", self._get("RUNTIME_LANGUAGE")),
                cast("str", self._get("NODE_VERSION")),
                cast("str", self._get("PYTHON_VERSION")),
                self._get("WORKING_DIRECTORY") or ".",
                self._get("SAM_ADDOPTS") or "",
                env=env,
            )
        except SubprocessError as exc:
            if exc.returncode == _EXIT_WORKING_DIR_NOT_FOUND:
                working_dir = self._get("WORKING_DIRECTORY") or "."
                raise WorkingDirectoryNotFoundError(working_dir) from exc
            if exc.returncode == _EXIT_NVM_NOT_FOUND:
                raise NvmNotFoundError from exc
            if action == "build":
                raise SamBuildError(exc.returncode) from exc
            raise SamDeployError(account_id, exc.returncode) from exc

    def _resolve_stack_name(self) -> str:
        stack_name: str | None = self._get("STACK_NAME")
        return stack_name or get_repo_name()
