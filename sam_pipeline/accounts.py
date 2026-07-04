"""Account configuration helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sam_pipeline.exceptions import InvalidAccountConfigError

_ENTRY_RE = re.compile(r"^(\d{12})(?::([a-z0-9-]+))?$")


@dataclass(frozen=True)
class AccountTarget:
    """A resolved target account."""

    account_id: str
    region: str


def parse_account_ids(raw: str, default_region: str) -> list[AccountTarget]:
    """Parse the AWS_ACCOUNT_IDS environment variable.

    Expected format: ``ACCOUNT_ID:REGION`` entries separated by commas.
    The ``:REGION`` suffix is optional; ``default_region`` is used when omitted.

    Examples::

        "123456789012:us-east-1"
        "123456789012:us-east-1,987654321098:ap-southeast-2"
        "123456789012"   # uses default_region

    Args:
        raw: Raw value of the AWS_ACCOUNT_IDS variable.
        default_region: Fallback region when not specified per-account.

    Returns:
        List of AccountTarget instances.

    Raises:
        InvalidAccountConfigError: When any entry cannot be parsed.

    """
    targets: list[AccountTarget] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        match = _ENTRY_RE.match(entry)
        if not match:
            raise InvalidAccountConfigError(
                f"Invalid account entry '{entry}'. "
                "Expected format: ACCOUNT_ID or ACCOUNT_ID:REGION "
                "(e.g. '123456789012:us-east-1')."
            )
        account_id, region = match.group(1), match.group(2) or default_region
        targets.append(AccountTarget(account_id=account_id, region=region))
    return targets
