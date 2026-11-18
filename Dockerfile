FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY libraries.yaml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["global-library-mcp", "web", "--host", "0.0.0.0", "--port", "8000"]
