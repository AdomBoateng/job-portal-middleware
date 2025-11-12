from celery import Celery
from app.cron.config import Config

celery_app = Celery("cron", include=["app.cron.task"])
celery_app.config_from_object(Config)

if __name__ == "__main__":
    celery_app.start()
