# uv-based image: uv binary + Python 3.12 (Debian) in one layer
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set working directory
WORKDIR /app

# Install system dependencies (git for cloning, nodejs for mermaid validation)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Leverage Docker layer cache: copy only dependency manifests first
COPY pyproject.toml uv.lock README.md .python-version ./

# Install locked runtime deps into .venv without the project itself
RUN uv sync --frozen --no-install-project --no-group dev

# Copy project source
COPY codewiki ./codewiki
COPY img ./img

# Install the project itself (still frozen, no dev extras)
RUN uv sync --frozen --no-group dev

# Create output directories
RUN mkdir -p output/cache output/temp output/docs output/dependency_graphs

# Make the uv-managed venv the default PATH so `codewiki` / `python` resolve there
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Default command (uses venv python)
CMD ["python", "codewiki/run_web_app.py", "--host", "0.0.0.0", "--port", "8000"]
