FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/projects

WORKDIR /workspace/projects

COPY projects/academic_search/requirements.runtime.txt /tmp/academic-requirements.txt
COPY apps/python-sdk /tmp/firecrawl-python-sdk

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /tmp/academic-requirements.txt \
    && python -m pip install /tmp/firecrawl-python-sdk

COPY projects/academic_search /workspace/projects/academic_search

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "academic_search.service:app", "--host", "0.0.0.0", "--port", "8010"]

FROM runtime AS test

COPY projects/academic_search/requirements.test.txt /tmp/academic-test-requirements.txt

RUN python -m pip install -r /tmp/academic-test-requirements.txt

CMD ["python", "-m", "pytest", "-q", "academic_search/tests/test_academic_search.py", "academic_search/tests/test_firecrawl_research.py", "academic_search/tests/test_service.py"]
