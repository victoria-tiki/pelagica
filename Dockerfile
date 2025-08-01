# Use slim Python image with Debian base
FROM python:3.12-slim

# Set environment vars
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV POETRY_VIRTUALENVS_CREATE=false

# Install only essential build tools and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git wget libssl-dev libffi-dev libbz2-dev \
    liblzma-dev libsqlite3-dev zlib1g-dev libxml2-dev libxmlsec1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install poetry and rembg early
RUN pip install --upgrade pip && pip install poetry rembg

# Set working dir
WORKDIR /pelagica

# Copy project code
COPY . .

# Install Python dependencies via Poetry
RUN poetry install

# Download U-2-Net model for rembg (if needed)
RUN python3 -c "from rembg import session_factory; session_factory.new_session('u2net')"

# Clean up build tools and caches
RUN apt-get purge -y build-essential && \
    apt-get autoremove -y && \
    rm -rf ~/.cache/pip /root/.cache/pip /var/lib/apt/lists/*
    

# Default command
CMD ["python3", "app.py"]

