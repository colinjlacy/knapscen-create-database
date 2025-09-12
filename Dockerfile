# Use Python slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application script
COPY create_database_schema.py .

# Set ownership and make script executable
RUN chown appuser:appuser /app/create_database_schema.py && \
    chmod +x /app/create_database_schema.py

# Switch to non-root user
USER appuser

# Set the entry point
ENTRYPOINT ["python", "/app/create_database_schema.py"]
