"""Custom exceptions for the SAM pipeline."""


class SamPipelineError(Exception):
    """Base exception for the SAM pipeline."""


class SamBuildError(SamPipelineError):
    """SAM build failed."""

    def __init__(self, returncode: int) -> None:
        super().__init__(f"sam build failed with return code {returncode}")


class SamDeployError(SamPipelineError):
    """SAM deploy failed."""

    def __init__(self, account_id: str, returncode: int) -> None:
        super().__init__(
            f"sam deploy to account {account_id} failed with return code {returncode}"
        )


class SubprocessError(SamPipelineError):
    """A subprocess exited with a non-zero return code."""

    def __init__(self, returncode: int, command: str) -> None:
        self.returncode = returncode
        self.command = command
        super().__init__(f"Command '{command}' failed with return code {returncode}")


class NvmNotFoundError(SamPipelineError):
    """NVM was not found in the Docker image."""

    def __init__(self) -> None:
        super().__init__(
            "NVM not found. Ensure the Docker image was built correctly and NVM_DIR is set."
        )


class WorkingDirectoryNotFoundError(SamPipelineError):
    """The specified working directory does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Working directory not found: {path}")


class InvalidAccountConfigError(SamPipelineError):
    """Account configuration is invalid."""


class ValidationError(SamPipelineError):
    """Input variable validation failed."""

    def __init__(self, errors: dict) -> None:
        super().__init__(f"Validation failed: {errors}")
