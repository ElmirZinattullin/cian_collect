# -*- coding: utf-8 -*-
"""
Celery-задача для ежедневного запуска опроса CIAN в 20:00 по Europe/Berlin.

Запуск в Docker Compose:
  docker compose up -d --build
"""

import os
from celery import Celery
from celery.schedules import crontab

from cian_meta_collect import run_collection, CSV_PATH
from utils import send_email

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery("cian_celery_tasks", broker=BROKER_URL, backend=RESULT_BACKEND)
app.conf.update(
    timezone="Europe/Berlin",
    enable_utc=False,
    beat_schedule={
        "collect-cian-counts-everyday-20-00": {
            "task": "cian_celery_tasks.collect_cian_counts",
            "schedule": crontab(hour=20, minute=0),
            "args": (),
        },
    },
)


@app.task(name="cian_celery_tasks.collect_cian_counts")
def collect_cian_counts(csv_path: str = None) -> str:
    """
    Celery-таск. Возвращает путь к файлу CSV.
    После сбора — отправляет письмо с вложением CSV.
    """
    path = csv_path or CSV_PATH
    out_path = run_collection(path)

    try:
        send_email(body="Во вложении свежий CSV с количеством объявлений.", attachments=[out_path])
    except Exception as e:
        # Не падаем из-за почты — но возвращаем информацию в результат
        return f"{out_path} (email error: {e})"

    return out_path
