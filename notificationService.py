from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os
import socket
import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("notification_service")


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
SERVICE_DISCOVERY_URL = os.getenv("SERVICE_DISCOVERY_URL", "http://service_discovery:8500")
PORT = int(os.getenv("PORT", 8600))

app = FastAPI(title="Notifications Service")


class Alert(BaseModel):
    service: str
    status: str
    message: str
    timestamp: str

@app.post("/notify")
async def notify(alert: Alert):
    """Receive alert from Service Discovery and send Telegram message"""
    text = (
        f"*Service Alert!*\n"
        f"*Service:* {alert.service}\n"
        f"*Status:* {alert.status.upper()}\n"
        f"*Time:* {alert.timestamp}\n"
        f"*Message:* {alert.message}"
    )

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                TELEGRAM_URL,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown"
                }
            )
        logger.info("Telegram notification sent successfully")
        return {"message": "Telegram notification sent"}
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return {"error": f"Failed to send Telegram message: {e}"}



async def register_service(retries=5, delay=5):
    """Register this Notification Service with the Service Discovery."""
    host = socket.gethostbyname(socket.gethostname())
    payload = {
        "service_name": "notification-service",
        "service_id": f"notification-{host}",
        "host": host,
        "port": PORT,
        "health_check_url": "/health",  
        "metadata": {"version": "1.0.0", "environment": "docker"},
    }

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{SERVICE_DISCOVERY_URL}/register", json=payload)
                res.raise_for_status()
                logger.info(f"Registered with Service Discovery: {res.json()}")
                return
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{retries} failed to register: {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
            else:
                logger.error("Could not register with Service Discovery after retries.")


@app.on_event("startup")
async def startup_event():
    logger.info("Notifications Service starting up...")
    asyncio.create_task(register_service())

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)