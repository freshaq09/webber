FROM python:3.11-slim

# Install system dependencies including wget
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Set environment variable
ENV PORT=8080

# Run the application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"] 