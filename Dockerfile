# 🐍 Base image
FROM python:3.11-slim

# 🗂️ Set working directory
WORKDIR /app

# ⚡ Copy dependency list first (improves build caching)
COPY requirements.txt .

# 🧩 Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 📦 Copy all source files (both serviceDiscovery.py and notificationService.py)
COPY . .

# 🧱 Expose default Service Discovery port
EXPOSE 8500

# 🧱 Expose Notification Service port (optional)
EXPOSE 8600


CMD ["python", "serviceDiscovery.py"]
