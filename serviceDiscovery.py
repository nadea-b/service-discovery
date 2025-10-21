from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import uvicorn
from contextlib import asynccontextmanager
import asyncio
import httpx
from io import StringIO

# Configure logging to both console and memory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# In-memory log storage
log_buffer = StringIO()
log_handler = logging.StreamHandler(log_buffer)
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(log_handler)

# In-memory service registry
service_registry: Dict[str, Dict[str, Any]] = {}

# Health check task
health_check_task = None

# Configuration
HEALTH_CHECK_INTERVAL = 30  # seconds
HEALTH_CHECK_TIMEOUT = 5    # seconds
CRITICAL_LOAD_THRESHOLD = 80  # percentage

# Pydantic models
class ServiceRegistration(BaseModel):
    service_name: str = Field(..., description="Name of the service")
    service_id: str = Field(..., description="Unique identifier for this instance")
    host: str = Field(..., description="Host/IP address of the service")
    port: int = Field(..., description="Port number of the service")
    health_check_url: Optional[str] = Field(None, description="Health check endpoint")
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional metadata")

class ServiceInfo(BaseModel):
    service_name: str
    service_id: str
    host: str
    port: int
    health_check_url: Optional[str]
    metadata: Dict[str, str]
    registered_at: str
    last_heartbeat: str
    last_health_check: Optional[str]
    status: str
    health_status: Optional[str]
    response_time_ms: Optional[float]

class HeartbeatRequest(BaseModel):
    service_id: str = Field(..., description="Service instance ID")

class ServiceHealth(BaseModel):
    service_id: str
    service_name: str
    status: str
    health_status: str
    last_check: str
    response_time_ms: float
    details: Optional[Dict[str, Any]]

# Health monitoring
async def check_service_health(service_id: str, service_info: Dict) -> Dict:
    """Check health of a single service"""
    if not service_info.get("health_check_url"):
        return {
            "status": "unknown",
            "response_time_ms": 0,
            "error": "No health check URL configured"
        }
    
    health_url = f"http://{service_info['host']}:{service_info['port']}{service_info['health_check_url']}"
    
    try:
        start_time = datetime.now()
        async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
            response = await client.get(health_url)
            end_time = datetime.now()
            
        response_time = (end_time - start_time).total_seconds() * 1000  # ms
        
        if response.status_code == 200:
            health_data = response.json() if response.content else {}
            return {
                "status": "healthy",
                "response_time_ms": response_time,
                "details": health_data
            }
        else:
            return {
                "status": "unhealthy",
                "response_time_ms": response_time,
                "error": f"HTTP {response.status_code}"
            }
    
    except httpx.TimeoutException:
        logger.warning(f"Health check timeout for {service_info['service_name']} (ID: {service_id})")
        return {
            "status": "unhealthy",
            "response_time_ms": HEALTH_CHECK_TIMEOUT * 1000,
            "error": "Timeout"
        }
    except Exception as e:
        logger.error(f"Health check failed for {service_info['service_name']} (ID: {service_id}): {str(e)}")
        return {
            "status": "unhealthy",
            "response_time_ms": 0,
            "error": str(e)
        }

async def periodic_health_check():
    """Periodically check health of all registered services"""
    logger.info(f"Starting periodic health checks (every {HEALTH_CHECK_INTERVAL}s)")
    
    while True:
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            
            if not service_registry:
                continue
            
            logger.info(f"Running health checks for {len(service_registry)} services...")
            
            for service_id, service_info in service_registry.items():
                health_result = await check_service_health(service_id, service_info)
                
                # Update service registry
                service_registry[service_id]["last_health_check"] = datetime.now().isoformat()
                service_registry[service_id]["health_status"] = health_result["status"]
                service_registry[service_id]["response_time_ms"] = health_result.get("response_time_ms", 0)
                
                # Log alerts for unhealthy services
                if health_result["status"] == "unhealthy":
                    logger.error(f"ALERT: Service {service_info['service_name']} (ID: {service_id}) is UNHEALTHY! Error: {health_result.get('error', 'Unknown')}")
                    service_registry[service_id]["status"] = "unhealthy"
                
                # Check for critical load (slow response times)
                response_time = health_result.get("response_time_ms", 0)
                if response_time > 1000:  # > 1 second
                    logger.warning(f"LOAD WARNING: Service {service_info['service_name']} response time: {response_time:.2f}ms")
                
                # Log healthy status at debug level
                elif health_result["status"] == "healthy":
                    logger.debug(f"Service {service_info['service_name']} is healthy (response: {response_time:.2f}ms)")
            
            logger.info(f"Health check cycle completed")
            
        except Exception as e:
            logger.error(f"Error in periodic health check: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global health_check_task
    
    logger.info("Service Discovery starting up...")
    logger.info("Service registry initialized")
    
    # Start health check background task
    health_check_task = asyncio.create_task(periodic_health_check())
    
    yield
    
    # Cleanup
    logger.info("Service Discovery shutting down...")
    if health_check_task:
        health_check_task.cancel()
    logger.info(f"Total services registered during session: {len(service_registry)}")

app = FastAPI(
    title="Service Discovery",
    description="Centralized service registry with health monitoring",
    version="1.1.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Root endpoint - Service Discovery info"""
    healthy_services = sum(1 for s in service_registry.values() if s.get("health_status") == "healthy")
    
    return {
        "service": "Service Discovery",
        "status": "running",
        "version": "1.1.0",
        "registered_services": len(service_registry),
        "healthy_services": healthy_services,
        "unhealthy_services": len(service_registry) - healthy_services,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register_service(registration: ServiceRegistration):
    """Register a new service instance"""
    try:
        service_key = registration.service_id
        
        if service_key in service_registry:
            logger.warning(f"Service {registration.service_name} (ID: {service_key}) already registered, updating...")
        else:
            logger.info(f"New service registration: {registration.service_name} (ID: {service_key})")
        
        service_registry[service_key] = {
            "service_name": registration.service_name,
            "service_id": registration.service_id,
            "host": registration.host,
            "port": registration.port,
            "health_check_url": registration.health_check_url,
            "metadata": registration.metadata or {},
            "registered_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "last_health_check": None,
            "status": "healthy",
            "health_status": "unknown",
            "response_time_ms": 0
        }
        
        logger.info(f"Service registered: {registration.service_name} at {registration.host}:{registration.port}")
        logger.info(f"Total active services: {len(service_registry)}")
        
        return {
            "message": "Service registered successfully",
            "service_id": registration.service_id,
            "registered_at": service_registry[service_key]["registered_at"]
        }
    
    except Exception as e:
        logger.error(f"Error registering service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register service: {str(e)}"
        )

@app.delete("/deregister/{service_id}", status_code=status.HTTP_200_OK)
async def deregister_service(service_id: str):
    """Deregister a service instance"""
    try:
        if service_id not in service_registry:
            logger.warning(f"Attempted to deregister non-existent service: {service_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not found"
            )
        
        service_info = service_registry[service_id]
        logger.info(f"Deregistering service: {service_info['service_name']} (ID: {service_id})")
        
        del service_registry[service_id]
        
        logger.info(f"Service deregistered successfully: {service_id}")
        logger.info(f"Remaining active services: {len(service_registry)}")
        
        return {
            "message": "Service deregistered successfully",
            "service_id": service_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deregistering service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deregister service: {str(e)}"
        )

@app.post("/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat(heartbeat_req: HeartbeatRequest):
    """Receive heartbeat from a service"""
    try:
        service_id = heartbeat_req.service_id
        
        if service_id not in service_registry:
            logger.warning(f"Heartbeat from unregistered service: {service_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not registered"
            )
        
        service_registry[service_id]["last_heartbeat"] = datetime.now().isoformat()
        if service_registry[service_id]["health_status"] != "unhealthy":
            service_registry[service_id]["status"] = "healthy"
        
        logger.debug(f"Heartbeat from: {service_registry[service_id]['service_name']}")
        
        return {
            "message": "Heartbeat received",
            "service_id": service_id,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing heartbeat: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process heartbeat: {str(e)}"
        )

@app.get("/services", response_model=List[ServiceInfo])
async def get_all_services():
    """Get all registered services"""
    try:
        logger.debug(f"Listing all services - Total: {len(service_registry)}")
        
        services = []
        for service_id, info in service_registry.items():
            services.append(ServiceInfo(**info))
        
        return services
    
    except Exception as e:
        logger.error(f"Error retrieving services: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve services: {str(e)}"
        )

@app.get("/services/{service_name}", response_model=List[ServiceInfo])
async def get_service_by_name(service_name: str):
    """Get all instances of a service by name"""
    try:
        logger.info(f"Looking up service: {service_name}")
        
        services = []
        for service_id, info in service_registry.items():
            if info["service_name"] == service_name:
                services.append(ServiceInfo(**info))
        
        if not services:
            logger.warning(f"No instances found for service: {service_name}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No instances found for service: {service_name}"
            )
        
        logger.info(f"Found {len(services)} instance(s) of {service_name}")
        return services
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving service {service_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve service: {str(e)}"
        )

@app.get("/service/{service_id}", response_model=ServiceInfo)
async def get_service_by_id(service_id: str):
    """Get a specific service instance by ID"""
    try:
        logger.debug(f"Looking up service by ID: {service_id}")
        
        if service_id not in service_registry:
            logger.warning(f"Service not found: {service_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not found"
            )
        
        return ServiceInfo(**service_registry[service_id])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving service by ID: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve service: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    healthy_count = sum(1 for s in service_registry.values() if s.get("health_status") == "healthy")
    
    return {
        "status": "healthy",
        "service": "service-discovery",
        "timestamp": datetime.now().isoformat(),
        "registered_services": len(service_registry),
        "healthy_services": healthy_count
    }

# NEW: Service health status endpoint
@app.get("/services/{service_name}/health", response_model=List[ServiceHealth])
async def get_service_health(service_name: str):
    """Get health status of all instances of a service"""
    try:
        logger.info(f"Getting health status for service: {service_name}")
        
        health_statuses = []
        for service_id, info in service_registry.items():
            if info["service_name"] == service_name:
                health_statuses.append(ServiceHealth(
                    service_id=info["service_id"],
                    service_name=info["service_name"],
                    status=info["status"],
                    health_status=info.get("health_status", "unknown"),
                    last_check=info.get("last_health_check", "never"),
                    response_time_ms=info.get("response_time_ms", 0),
                    details=None
                ))
        
        if not health_statuses:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No instances found for service: {service_name}"
            )
        
        return health_statuses
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting health status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get health status: {str(e)}"
        )

# NEW: Check specific service health now
@app.post("/services/{service_id}/check-health")
async def check_health_now(service_id: str):
    """Manually trigger health check for a specific service"""
    try:
        if service_id not in service_registry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not found"
            )
        
        service_info = service_registry[service_id]
        logger.info(f"Manual health check requested for {service_info['service_name']}")
        
        health_result = await check_service_health(service_id, service_info)
        
        # Update registry
        service_registry[service_id]["last_health_check"] = datetime.now().isoformat()
        service_registry[service_id]["health_status"] = health_result["status"]
        service_registry[service_id]["response_time_ms"] = health_result.get("response_time_ms", 0)
        
        return {
            "service_id": service_id,
            "service_name": service_info["service_name"],
            "health_status": health_result["status"],
            "response_time_ms": health_result.get("response_time_ms", 0),
            "details": health_result.get("details"),
            "error": health_result.get("error"),
            "checked_at": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check health: {str(e)}"
        )

# NEW: Download logs endpoint
@app.get("/logs", response_class=PlainTextResponse)
async def download_logs():
    """Download system logs"""
    try:
        logger.info("Logs download requested")
        
        # Get current logs from buffer
        log_content = log_buffer.getvalue()
        
        if not log_content:
            return "No logs available"
        
        return PlainTextResponse(
            content=log_content,
            headers={
                "Content-Disposition": f"attachment; filename=service_discovery_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            }
        )
    
    except Exception as e:
        logger.error(f"Error downloading logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download logs: {str(e)}"
        )

# NEW: Get recent logs (last N lines)
@app.get("/logs/recent")
async def get_recent_logs(lines: int = 100):
    """Get recent log lines"""
    try:
        log_content = log_buffer.getvalue()
        log_lines = log_content.split('\n')
        recent_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
        
        return {
            "total_lines": len(log_lines),
            "returned_lines": len(recent_lines),
            "logs": recent_lines
        }
    
    except Exception as e:
        logger.error(f"Error getting recent logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent logs: {str(e)}"
        )

# System statistics
@app.get("/stats")
async def get_system_stats():
    """Get system statistics"""
    healthy = sum(1 for s in service_registry.values() if s.get("health_status") == "healthy")
    unhealthy = sum(1 for s in service_registry.values() if s.get("health_status") == "unhealthy")
    unknown = sum(1 for s in service_registry.values() if s.get("health_status") == "unknown")
    
    avg_response_time = 0
    if service_registry:
        total_response = sum(s.get("response_time_ms", 0) for s in service_registry.values())
        avg_response_time = total_response / len(service_registry)
    
    return {
        "total_services": len(service_registry),
        "healthy_services": healthy,
        "unhealthy_services": unhealthy,
        "unknown_services": unknown,
        "average_response_time_ms": round(avg_response_time, 2),
        "health_check_interval_seconds": HEALTH_CHECK_INTERVAL,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    logger.info("Starting Service Discovery on port 8500")
    uvicorn.run(app, host="0.0.0.0", port=8500)