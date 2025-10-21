FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY serviceDiscovery.py .

# Expose the port
EXPOSE 8500

# Run the application
CMD ["python", "serviceDiscovery.py"]