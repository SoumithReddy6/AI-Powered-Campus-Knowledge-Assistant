from __future__ import annotations

import json

from campus_assistant.ingestion.pipeline import IngestionPipeline
from campus_assistant.utils.logging import configure_logging


if __name__ == "__main__":
    configure_logging()
    summary = IngestionPipeline().run()
    print(json.dumps(summary, indent=2))
