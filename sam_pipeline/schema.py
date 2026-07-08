"""Validation schema for pipeline input variables."""

from typing import Any

schema: dict[str, Any] = {
    "AWS_ACCOUNT_ID": {
        "type": "string",
        "required": False,
        "minlength": 12,
        "maxlength": 12,
    },
    "AWS_ACCOUNT_IDS": {
        "type": "string",
        "required": False,
    },
    "AWS_REGION": {
        "type": "string",
        "required": False,
        "default": "us-east-1",
    },
    "DEPLOYER_ROLE_NAME": {
        "type": "string",
        "required": False,
        "default": "DeployerAccess",
    },
    "RUNTIME_LANGUAGE": {
        "type": "string",
        "required": False,
        "default": "nodejs",
        "allowed": ["nodejs", "python"],
    },
    "NODE_VERSION": {
        "type": "string",
        "required": False,
        "default": "20",
    },
    "PYTHON_VERSION": {
        "type": "string",
        "required": False,
        "default": "3.14.0",
    },
    "WORKING_DIRECTORY": {
        "type": "string",
        "required": False,
        "default": ".",
    },
    "STACK_NAME": {
        "type": "string",
        "required": False,
    },
    "SAM_ADDOPTS": {
        "type": "string",
        "required": False,
        "default": "",
    },
    "DEBUG": {
        "type": "boolean",
        "required": False,
        "default": False,
        "coerce": bool,
    },
}
