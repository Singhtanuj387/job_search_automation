# Official Python 3.11 slim base image
FROM python:3.11-slim

# Prevent interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (Hugging Face Spaces runs containers as UID 1000)
RUN useradd -m -u 1000 user && \
    mkdir -p /ms-playwright && \
    chmod -R 777 /ms-playwright

WORKDIR /home/user/app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium and system dependencies as root
RUN playwright install --with-deps chromium && \
    chmod -R 777 /ms-playwright

# Copy application source code
COPY . .

# Ensure runtime directories exist and are owned by user 1000
RUN mkdir -p /home/user/app/data /home/user/app/uploads /home/user/app/logs && \
    chown -R user:user /home/user

# Switch to non-root user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

EXPOSE 7860

# Run FastAPI backend with Uvicorn on Hugging Face Spaces port 7860
CMD ["uvicorn", "web.backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
