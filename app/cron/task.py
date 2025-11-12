import websockets
import asyncio
import json
import logging
import os
from dotenv import load_dotenv

from app.cron import celery_app


load_dotenv()


SERVER_WS_URL = os.getenv("SERVER_WS_URL")



logger = logging.getLogger("app.cron.task")

@celery_app.task(auto_retry=True, max_retries=3)
def send_ai_results_to_server(results: dict, server_ws_url: str = SERVER_WS_URL) -> bool:
    """Send a job application to the external AI agent via WebSocket.
    
    This task connects to the AI agent's WebSocket URL, sends the application
    data as JSON, and optionally waits for an acknowledgment.
    """
    
    async def _send_results(results: dict, ws_url: str):
        try:
            async with websockets.connect(ws_url, ping_interval=20, close_timeout=5) as ws:
                # Send the results data
                await ws.send(json.dumps({
                    "action": "results",
                    "results": results
                }, default=str))
                logger.info("Sent AI results to server")
                
                # Optionally wait for acknowledgment (with timeout)
                try:
                    ack = await asyncio.wait_for(ws.recv(), timeout=3)
                    logger.info(f"Server acknowledged: {ack}")
                except asyncio.TimeoutError:
                    logger.info("No acknowledgment received from server (timeout)")
        except Exception as e:
            logger.error(f"Failed to send results to server: {e}")
            return False
    
    return asyncio.run(_send_results(results, server_ws_url))