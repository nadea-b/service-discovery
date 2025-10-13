from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import uvicorn
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# In-memory service registry
service_registry: Dict[str, Dict[str, any]] = {}

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
    status: str

class HeartbeatRequest(BaseModel):
    service_id: str = Field(..., description="Service instance ID")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service Discovery starting up...")
    logger.info("Service registry initialized")
    yield
    logger.info("Service Discovery shutting down...")
    logger.info(f"Total services registered during session: {len(service_registry)}")

app = FastAPI(
    title="Service Discovery",
    description="Centralized service registry for microservices architecture",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Root endpoint - Service Discovery info"""
    logger.info("Root endpoint accessed")
    return {
        "service": "Service Discovery",
        "status": "running",
        "version": "1.0.0",
        "registered_services": len(service_registry),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register_service(registration: ServiceRegistration):
    """Register a new service instance"""
    try:
        service_key = registration.service_id
        
        # Check if service already exists
        if service_key in service_registry:
            logger.warning(f"Service {registration.service_name} (ID: {service_key}) already registered, updating...")
        else:
            logger.info(f"New service registration: {registration.service_name} (ID: {service_key})")
        
        # Store service information
        service_registry[service_key] = {
            "service_name": registration.service_name,
            "service_id": registration.service_id,
            "host": registration.host,
            "port": registration.port,
            "health_check_url": registration.health_check_url,
            "metadata": registration.metadata or {},
            "registered_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "status": "healthy"
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
        logger.info(f"🗑️  Deregistering service: {service_info['service_name']} (ID: {service_id})")
        
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
        service_registry[service_id]["status"] = "healthy"
        
        logger.debug(f"Heartbeat received from: {service_registry[service_id]['service_name']} (ID: {service_id})")
        
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
        logger.info(f"Listing all services - Total: {len(service_registry)}")
        
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
        logger.info(f"Looking up service by ID: {service_id}")
        
        if service_id not in service_registry:
            logger.warning(f"Service not found: {service_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID {service_id} not found"
            )
        
        logger.info(f"Service found: {service_registry[service_id]['service_name']}")
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
    logger.debug("Health check performed")
    return {
        "status": "healthy",
        "service": "service-discovery",
        "timestamp": datetime.now().isoformat(),
        "registered_services": len(service_registry)
    }

if __name__ == "__main__":
    logger.info("Starting Service Discovery on port 8500")
    uvicorn.run(app, host="0.0.0.0", port=8500)