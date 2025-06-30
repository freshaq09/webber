FROM python:3.11-slim

# Install system dependencies including wget and build tools
RUN apt-get update && apt-get install -y \
    wget \
    gcc \
    g++ \
    make \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway will set the actual port)
EXPOSE $PORT

# Run the application with proper port binding
CMD gunicorn app:app --bind 0.0.0.0:$PORT 