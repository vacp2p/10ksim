FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY dst_dashboard/ ./dst_dashboard/

# Install uv for faster dependency installation
RUN pip install --no-cache-dir uv

# Install dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# Create database directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "dst_dashboard.main:app", "--host", "0.0.0.0", "--port", "8000"]
