FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[anthropic,openai,google]" && useradd -m app
USER app
ENV MARS_LOG_JSON=true
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "mars.api.app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
