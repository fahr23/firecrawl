"""Each request logs one self-contained ACCESS line (method, path, status, duration),
so concurrent requests can't be mis-paired the way the multi-line block was."""
import logging
import re

from fastapi.testclient import TestClient

from api.main import app


def test_access_line_has_method_path_status_and_duration(caplog):
    caplog.set_level(logging.INFO, logger="api.main")
    TestClient(app).get("/api/external/v1/nonexistent-route?x=1")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("ACCESS ")]
    assert lines, "no ACCESS line logged"
    assert re.fullmatch(r"ACCESS GET /api/external/v1/nonexistent-route\?x=1 404 \d+\.\d{3}s", lines[-1])
