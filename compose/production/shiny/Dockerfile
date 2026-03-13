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

# Copy package metadata first so the pip install layer is cached as long as
# pyproject.toml / README.md don't change.
COPY pyproject.toml README.md ./

# Install dependencies (no editable install — production image)
RUN pip install --no-cache-dir .

# Copy application source after installing deps to maximise layer reuse
COPY tfbpshiny/ tfbpshiny/
COPY configure_logger.py .

# Run as a non-root user
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

# Shiny listens on 0.0.0.0:8000 inside the container; host/port can be
# overridden via the compose `command:` key.
EXPOSE 8000

CMD ["python", "-m", "tfbpshiny", "--log-level", "INFO", "shiny", "--host", "0.0.0.0"]
