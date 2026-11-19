FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY libraries.yaml ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 appuser

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
USER appuser
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 CMD python -c "import json, urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/health'))['ok']"
CMD ["global-library-mcp", "web", "--host", "0.0.0.0", "--port", "8000"]
