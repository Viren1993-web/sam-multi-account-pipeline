"""Unit tests for account parsing, utils, and pipeline logic."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from sam_pipeline.__main__ import _load_pipeline_dotenv
from sam_pipeline.accounts import AccountTarget, parse_account_ids
from sam_pipeline.exceptions import InvalidAccountConfigError, SamValidateError, SubprocessError
from sam_pipeline.pipe import SamPipeline
from sam_pipeline.utils import bool_from_env, get_repo_name, running_in_ci

if TYPE_CHECKING:
    from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# parse_account_ids
# ──────────────────────────────────────────────────────────────────────────────


class TestParseAccountIds:
    def test_single_account_with_region(self) -> None:
        targets = parse_account_ids(
            "123456789012:us-east-1",
            "ap-southeast-2",
        )
        assert targets == [  # noqa: S101
            AccountTarget(account_id="123456789012", region="us-east-1"),
        ]

    def test_single_account_without_region_uses_default(self) -> None:
        targets = parse_account_ids(
            "123456789012",
            "ap-southeast-2",
        )
        assert targets == [  # noqa: S101
            AccountTarget(account_id="123456789012", region="ap-southeast-2"),
        ]

    def test_multiple_accounts(self) -> None:
        targets = parse_account_ids(
            "123456789012:us-east-1,987654321098:ap-southeast-2",
            "eu-west-1",
        )
        assert targets == [  # noqa: S101
            AccountTarget(account_id="123456789012", region="us-east-1"),
            AccountTarget(account_id="987654321098", region="ap-southeast-2"),
        ]

    def test_ignores_blank_entries(self) -> None:
        targets = parse_account_ids("123456789012:us-east-1,,", "us-east-1")
        assert len(targets) == 1  # noqa: S101

    def test_invalid_entry_raises(self) -> None:
        with pytest.raises(InvalidAccountConfigError, match="Invalid account entry"):
            parse_account_ids("not-an-account", "us-east-1")

    def test_short_account_id_raises(self) -> None:
        with pytest.raises(InvalidAccountConfigError):
            parse_account_ids("1234:us-east-1", "us-east-1")


# ──────────────────────────────────────────────────────────────────────────────
# bool_from_env
# ──────────────────────────────────────────────────────────────────────────────


class TestBoolFromEnv:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes"])
    def test_truthy_strings(self, value: str) -> None:
        assert bool_from_env(value) is True  # noqa: S101

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", ""])
    def test_falsy_strings(self, value: str) -> None:
        assert bool_from_env(value) is False  # noqa: S101

    def test_bool_true(self) -> None:
        assert bool_from_env(True) is True  # noqa: FBT003,S101

    def test_bool_false(self) -> None:
        assert bool_from_env(False) is False  # noqa: FBT003,S101

    def test_none(self) -> None:
        assert bool_from_env(None) is False  # noqa: S101


# ──────────────────────────────────────────────────────────────────────────────
# running_in_ci
# ──────────────────────────────────────────────────────────────────────────────


class TestRunningInCi:
    def test_true_when_ci_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        assert running_in_ci() is True  # noqa: S101

    def test_false_when_ci_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        assert running_in_ci() is False  # noqa: S101

    def test_false_when_ci_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "false")
        assert running_in_ci() is False  # noqa: S101


# ──────────────────────────────────────────────────────────────────────────────
# get_repo_name
# ──────────────────────────────────────────────────────────────────────────────


class TestGetRepoName:
    def test_github_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "my-org/my-repo")
        assert get_repo_name() == "my-repo"  # noqa: S101

    def test_bitbucket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.setenv("BITBUCKET_REPO_SLUG", "my-bb-repo")
        assert get_repo_name() == "my-bb-repo"  # noqa: S101


# ──────────────────────────────────────────────────────────────────────────────
# SamPipeline — input validation
# ──────────────────────────────────────────────────────────────────────────────


class TestSamPipelineValidation:
    def test_missing_accounts_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AWS_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("AWS_ACCOUNT_IDS", raising=False)
        pipe = SamPipeline()
        pipe._vars = pipe._load_and_validate()  # noqa: SLF001
        with pytest.raises(ValueError, match="No target accounts configured"):
            pipe._resolve_accounts()  # noqa: SLF001

    def test_single_account_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCOUNT_ID", "123456789012")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        pipe = SamPipeline()
        pipe._vars = pipe._load_and_validate()  # noqa: SLF001
        accounts = pipe._resolve_accounts()  # noqa: SLF001
        assert len(accounts) == 1  # noqa: S101
        assert accounts[0].account_id == "123456789012"  # noqa: S101
        assert accounts[0].region == "us-east-1"  # noqa: S101

    def test_multiple_accounts_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        expected_account_count = 2
        monkeypatch.setenv(
            "AWS_ACCOUNT_IDS",
            "123456789012:us-east-1,987654321098:ap-southeast-2",
        )
        pipe = SamPipeline()
        pipe._vars = pipe._load_and_validate()  # noqa: SLF001
        accounts = pipe._resolve_accounts()  # noqa: SLF001
        assert len(accounts) == expected_account_count  # noqa: S101

    def test_stack_name_defaults_to_repo_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "my-org/my-service")
        monkeypatch.delenv("STACK_NAME", raising=False)
        pipe = SamPipeline()
        pipe._vars = pipe._load_and_validate()  # noqa: SLF001
        assert pipe._resolve_stack_name() == "my-service"  # noqa: S101,SLF001

    def test_stack_name_uses_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STACK_NAME", "my-custom-stack")
        pipe = SamPipeline()
        pipe._vars = pipe._load_and_validate()  # noqa: SLF001
        assert pipe._resolve_stack_name() == "my-custom-stack"  # noqa: S101,SLF001

    def test_expand_sam_addopts_replaces_dollar_vars(self) -> None:
        pipe = SamPipeline()
        env = {
            "STAGE": "dev",
            "SECRET_VAL": "abc",
        }
        value = "--config-env $STAGE --parameter-overrides Stage=${STAGE} Key=$SECRET_VAL"
        expanded = pipe._expand_sam_addopts(value, env)  # noqa: SLF001
        assert expanded == "--config-env dev --parameter-overrides Stage=dev Key=abc"  # noqa: S101

    def test_expand_sam_addopts_uses_empty_for_missing_vars(self) -> None:
        pipe = SamPipeline()
        expanded = pipe._expand_sam_addopts("Stage=$MISSING", {})  # noqa: SLF001
        assert expanded == "Stage="  # noqa: S101


# ──────────────────────────────────────────────────────────────────────────────
# Dotenv loading
# ──────────────────────────────────────────────────────────────────────────────


class TestDotenvLoading:
    def test_loads_stage_file_from_working_directory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        env_file = tmp_path / ".env.dev"
        env_file.write_text("STAGE_FROM_FILE=dev\n", encoding="utf-8")

        monkeypatch.setenv("WORKING_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("STAGE", "dev")
        monkeypatch.delenv("STAGE_FROM_FILE", raising=False)

        _load_pipeline_dotenv()

        assert os.environ.get("STAGE_FROM_FILE") == "dev"  # noqa: S101

    def test_env_file_takes_priority_over_stage(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        stage_file = tmp_path / ".env.dev"
        explicit_file = tmp_path / ".env.custom"
        stage_file.write_text("KEY=from-stage\n", encoding="utf-8")
        explicit_file.write_text("KEY=from-custom\n", encoding="utf-8")

        monkeypatch.setenv("WORKING_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("STAGE", "dev")
        monkeypatch.setenv("ENV_FILE", ".env.custom")
        monkeypatch.delenv("KEY", raising=False)

        _load_pipeline_dotenv()

        assert os.environ.get("KEY") == "from-custom"  # noqa: S101

    def test_existing_environment_value_is_not_overridden(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("LOCKED_KEY=from-file\n", encoding="utf-8")

        monkeypatch.setenv("WORKING_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("LOCKED_KEY", "from-env")

        _load_pipeline_dotenv()

        assert os.environ.get("LOCKED_KEY") == "from-env"  # noqa: S101


# ──────────────────────────────────────────────────────────────────────────────
# SAM validate flow
# ──────────────────────────────────────────────────────────────────────────────


class TestSamValidateFlow:
    def test_deploy_runs_validate_before_build_and_deploy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pipe = SamPipeline()
        pipe._vars = {
            "DEPLOYER_ROLE_NAME": "DeployerAccess",
            "DEBUG": False,
            "STACK_NAME": "demo-stack",
            "RUNTIME_LANGUAGE": "nodejs",
            "NODE_VERSION": "24",
            "PYTHON_VERSION": "3.13.1",
            "WORKING_DIRECTORY": ".",
            "SAM_ADDOPTS": "--config-env dev",
        }

        calls: list[str] = []

        monkeypatch.setattr("sam_pipeline.pipe.assume_role_session", lambda **_: object())
        monkeypatch.setattr(
            "sam_pipeline.pipe.session_to_env",
            lambda *_: {
                "AWS_ACCESS_KEY_ID": "x",
                "AWS_SECRET_ACCESS_KEY": "y",
                "AWS_SESSION_TOKEN": "z",
                "AWS_REGION": "us-east-1",
            },
        )

        def fake_run_sam(
            action: str,
            stack_name: str,
            region: str,
            env: dict[str, str],
            account_id: str,
        ) -> None:
            _ = (stack_name, region, env, account_id)
            calls.append(action)

        monkeypatch.setattr(pipe, "_run_sam", fake_run_sam)

        pipe._deploy(AccountTarget(account_id="123456789012", region="us-east-1"))  # noqa: SLF001

        assert calls == ["validate", "build", "deploy"]  # noqa: S101

    def test_run_sam_maps_validate_failure_to_sam_validate_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pipe = SamPipeline()
        pipe._vars = {
            "RUNTIME_LANGUAGE": "nodejs",
            "NODE_VERSION": "24",
            "PYTHON_VERSION": "3.13.1",
            "WORKING_DIRECTORY": ".",
            "SAM_ADDOPTS": "",
        }

        def fake_run_command(*args: str, **kwargs: object) -> None:
            _ = (args, kwargs)
            raise SubprocessError(returncode=2, command="sam validate")

        monkeypatch.setattr("sam_pipeline.pipe.run_command", fake_run_command)

        with pytest.raises(SamValidateError, match="sam validate failed"):
            pipe._run_sam(  # noqa: SLF001
                "validate",
                "demo-stack",
                "us-east-1",
                {},
                "123456789012",
            )
