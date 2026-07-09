"""Entry point for the SAM pipeline runner."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from sam_pipeline.pipe import SamPipeline


def _load_pipeline_dotenv() -> None:
    """Load environment files for local and stage-aware deployments.

    Load order (earlier values win in CI/job env because override=False):
    1) WORKING_DIRECTORY/.env
    2) ENV_FILE (if provided)
    3) WORKING_DIRECTORY/.env.<STAGE> (when ENV_FILE is not set)
    """
    working_directory = Path(os.environ.get("WORKING_DIRECTORY", ".")).expanduser()
    env_file = (os.environ.get("ENV_FILE") or "").strip()
    stage = (os.environ.get("STAGE") or "").strip()

    load_dotenv(dotenv_path=working_directory / ".env", override=False)

    if env_file:
        env_path = Path(env_file).expanduser()
        if not env_path.is_absolute():
            env_path = working_directory / env_path
        load_dotenv(dotenv_path=env_path, override=False)
        return

    if stage:
        load_dotenv(dotenv_path=working_directory / f".env.{stage}", override=False)


def main() -> None:
    _load_pipeline_dotenv()
    pipe = SamPipeline()
    pipe.run()


if __name__ == "__main__":
    main()
