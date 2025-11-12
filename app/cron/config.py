import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")


class Config:
    broker_url = REDIS_URL
    result_backend = REDIS_URL
    time = "UTC"
    broker_connection_retry_on_startup = True
