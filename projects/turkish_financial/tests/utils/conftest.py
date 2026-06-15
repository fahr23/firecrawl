"""
Clear utils stubs injected at module-level by test_upstream_features.py.
This runs at conftest load time (before test files in this package are
collected), so the real modules are importable again.
"""
import sys

_STUBBED = [
    "utils.batch_job_manager",
    "utils.text_extractor",
    "utils.pdf_downloader",
    "utils.llm_analyzer",
    "utils.logger",
]

for _name in _STUBBED:
    sys.modules.pop(_name, None)
