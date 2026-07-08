"""Unit tests for account parsing, utils, and pipeline logic."""

from __future__ import annotations

import pytest

from sam_pipeline.accounts import AccountTarget, parse_account_ids
from sam_pipeline.exceptions import InvalidAccountConfigError
from sam_pipeline.pipe import SamPipeline
from sam_pipeline.utils import bool_from_env, get_repo_name, running_in_ci

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
