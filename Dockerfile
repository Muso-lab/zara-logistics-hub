# ==============================================================================
# Dockerfile: Zara Logistics Hub (Monterotondo Hub)
# Optimized for Google Cloud Run, Compute Engine (Docker/Nginx) & Local Containers
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Streamlit Production Configuration
ENV PORT=8080 \
    STREAMLIT_SERVER_PORT=8080 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

WORKDIR /app

# Install minimal OS dependencies for healthchecks & networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and reference data
COPY . .

# Create persistent/data directories and set permissions
RUN mkdir -p data data/templates data/downloads output \
    && chown -R 10001:10001 /app

# Run as non-root user for cloud security
USER 10001:10001

# Expose standard Cloud Run HTTP/WebSocket port
EXPOSE 8080

# Healthcheck for Cloud Run / Docker container orchestrator
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/_stcore/health || exit 1

# Start Streamlit application
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
