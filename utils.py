# -*- coding: utf-8 -*-
"""
Утилита отправки почты.

Отправляет письмо с темой "Ежедневный отчёт от ЦИАН"
на адрес zinattullinej@yandex.ru. Данные отправителя и SMTP
берутся из переменных окружения:

  SMTP_HOST (обязательно)
  SMTP_PORT (обязательно; обычно 465 для SSL)
  SMTP_USER (обязательно)
  SMTP_PASSWORD (обязательно)
  SMTP_FROM (необязательно, по умолчанию = SMTP_USER)

Пример использования:
    send_email(body="Привет!", attachments=["cian_counts.csv"])
"""

import os
import smtplib
import ssl
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import List, Optional

RECIPIENT = "zinattullinej@yandex.ru"
SUBJECT = "Ежедневный отчёт от ЦИАН"


def _attach_file(msg: MIMEMultipart, filepath: str):
    try:
        with open(filepath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(filepath)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)
    except Exception as e:
        # Не валим таску из-за вложения — просто добавим в текст
        current = msg.get_payload()
        msg.attach(MIMEText(f"\n[WARN] Не удалось приложить файл: {filepath} ({e})", "plain", "utf-8"))


def send_email(body: str = "", attachments: Optional[List[str]] = None):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "0") or 0)
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "")

    if not (smtp_host and smtp_port and smtp_user and smtp_password):
        raise RuntimeError("Отсутствуют обязательные переменные окружения SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD")

    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = RECIPIENT
    msg["Subject"] = SUBJECT
    msg.attach(MIMEText(body or "", "plain", "utf-8"))

    for fp in (attachments or []):
        _attach_file(msg, fp)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [RECIPIENT], msg.as_string())
