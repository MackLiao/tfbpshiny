FROM python:3.11-slim

# Ensures stdout/stderr are flushed immediately — required for live logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps: only what pip install actually needs at build time.
# git is required while any dependency installs from a VCS URL.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy all source files needed to build and install the package
COPY pyproject.toml README.md ./
COPY tfbpshiny/ tfbpshiny/
COPY configure_logger.py .

# Install the package and its dependencies
RUN pip install --no-cache-dir .

# Run as a non-root user
RUN useradd --no-create-home --shell /bin/false appuser && \
    mkdir -p /hf-cache && \
    chown appuser /hf-cache
USER appuser

# Shiny listens on 0.0.0.0:8000 inside the container; host/port can be
# overridden via the compose `command:` key.
EXPOSE 8000

CMD ["python", "-m", "tfbpshiny", "--log-level", "INFO", "shiny", "--host", "0.0.0.0"]
