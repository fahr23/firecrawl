FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.runtime.txt /app/requirements.runtime.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/requirements.runtime.txt

COPY . /app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test

COPY requirements.test.txt /app/requirements.test.txt

RUN python -m pip install -r /app/requirements.test.txt

CMD ["python", "-m", "pytest", "-q"]
