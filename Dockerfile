FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

ARG CMD_FILE=serviceDiscovery.py
ENV CMD_FILE=${CMD_FILE}

# Expose default Service Discovery port
EXPOSE 8500

# Expose Notification Service port (optional)
EXPOSE 8600


CMD ["sh", "-c", "python $CMD_FILE"]