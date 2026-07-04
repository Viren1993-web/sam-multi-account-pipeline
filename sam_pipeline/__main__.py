"""Entry point for the SAM pipeline runner."""

from dotenv import load_dotenv

from sam_pipeline.pipe import SamPipeline

load_dotenv(override=True)

if __name__ == "__main__":
    pipe = SamPipeline()
    pipe.run()
