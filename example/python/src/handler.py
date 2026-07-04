"""Hello World handler — Python example for sam-pipeline."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext


def handler(event: dict[str, Any], context: "LambdaContext") -> dict[str, Any]:
    """Return a simple greeting with the current account and region."""
    print(f"Event: {json.dumps(event)}")  # noqa: T201

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "Hello from sam-pipeline!",
                "account": os.environ.get("AWS_ACCOUNT_ID", "unknown"),
                "region": os.environ.get("AWS_REGION", "unknown"),
            }
        ),
    }
