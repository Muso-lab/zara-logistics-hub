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
    STREAMLIT_SERVER_ENABLE_STATIC_SERVING=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_THEME_BASE=light \
    STREAMLIT_THEME_PRIMARY_COLOR="#1E3A8A" \
    STREAMLIT_THEME_BACKGROUND_COLOR="#FFFFFF" \
    STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR="#F8FAFC" \
    STREAMLIT_THEME_TEXT_COLOR="#0F172A" 

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

# Patch Streamlit's default index.html and static folder with PWA manifest and icons
RUN python -c "\
import streamlit, os, re;\
st_dir = os.path.dirname(streamlit.__file__);\
idx_path = os.path.join(st_dir, 'static', 'index.html');\
html = open(idx_path, 'r', encoding='utf-8').read();\
pwa_tags = '''<title>Zara Logistics Hub</title>\\n    <link rel=\"manifest\" href=\"/app/static/manifest.json\">\\n    <meta name=\"theme-color\" content=\"#1E3A8A\">\\n    <meta name=\"mobile-web-app-capable\" content=\"yes\">\\n    <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\\n    <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\\n    <meta name=\"apple-mobile-web-app-title\" content=\"Zara Logistics\">\\n    <link rel=\"apple-touch-icon\" href=\"/app/static/icon-192.png\">''';\
html = re.sub(r'<title>.*?</title>', pwa_tags, html, count=1);\
open(idx_path, 'w', encoding='utf-8').write(html);\
import shutil;\
shutil.copy('static/manifest.json', os.path.join(st_dir, 'static', 'manifest.json'));\
shutil.copy('static/sw.js', os.path.join(st_dir, 'static', 'sw.js'));\
shutil.copy('static/icon-192.png', os.path.join(st_dir, 'static', 'icon-192.png'));\
shutil.copy('static/icon-512.png', os.path.join(st_dir, 'static', 'icon-512.png'));\
print('PWA patched in Streamlit successfully!')"


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
