# Service Discovery

A centralized service registry for microservices architecture built with Python FastAPI.

## Features

- **Service Registration**: Services can register themselves on startup
- **Service Deregistration**: Clean shutdown and deregistration
- **Heartbeat Mechanism**: Keep-alive signals from services
- **Service Discovery**: Query services by name or ID
- **Health Checks**: Built-in health check endpoint
- **Comprehensive Logging**: Detailed logs for all operations

## API Endpoints

### Root
- `GET /` - Service information and status

### Registration
- `POST /register` - Register a new service instance
  ```json
  {
    "service_name": "user-service",
    "service_id": "user-service-1",
    "host": "192.168.1.100",
    "port": 8080,
    "health_check_url": "/health",
    "metadata": {
      "version": "1.0.0",
      "environment": "production"
    }
  }
  ```

### Deregistration
- `DELETE /deregister/{service_id}` - Deregister a service instance

### Heartbeat
- `POST /heartbeat` - Send heartbeat from service
  ```json
  {
    "service_id": "user-service-1"
  }
  ```

### Discovery
- `GET /services` - Get all registered services
- `GET /services/{service_name}` - Get all instances of a service by name
- `GET /service/{service_id}` - Get a specific service instance by ID

### Health Check
- `GET /health` - Health check endpoint

## Docker Setup

### Build the Image
```bash
docker build -t service-discovery .
```

### Run with Docker
```bash
docker run -d -p 8500:8500 --name service-discovery service-discovery
```

### Run with Docker Compose
```bash
docker-compose up -d
```

## Local Development

### Prerequisites
- Python 3.11+
- pip

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
python main.py
```

The service will be available at `http://localhost:8500`

## Monitoring

Check service status:
```bash
curl http://localhost:8500/services
```

Check specific service:
```bash
curl http://localhost:8500/services/user-service
```

## Environment Variables

- `PORT` - Service port (default: 8500)
- `LOG_LEVEL` - Logging level (default: INFO)

## Logs

Logs include:
- Service registration/deregistration
- Heartbeat signals
- Service queries
- Error tracking
- Health check status

## Contributing

1. Create a feature branch
2. Make your changes
3. Submit a pull request

## License

MIT License

