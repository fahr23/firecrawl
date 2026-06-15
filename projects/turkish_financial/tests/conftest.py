"""
After collection is complete, remove any stubs injected at module-level by
test_upstream_features.py so that the real packages are importable by other
test modules (e.g. test_dependencies.py).
"""
import sys

_STUBS = [
    "aiohttp",
    "bs4",
    "pydantic",
    "dotenv",
    "utils.batch_job_manager",
    "utils.text_extractor",
    "utils.pdf_downloader",
    "utils.llm_analyzer",
    "utils.logger",
]


def pytest_collection_finish(session):
    for name in _STUBS:
        sys.modules.pop(name, None)
