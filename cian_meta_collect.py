#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт опрашивает CIAN API и сохраняет результат в CSV с разделителем `;`.
POST https://api.cian.ru/search-offers-index/v2/get-meta/

Комбинации:
  room in [1, 2, 3]
  price in [140000..200000] шаг 5000  (как "lte" в фильтре)

CSV формат:
Дата;1к - 140т.р.;1к - 145т.р.; ... ;3к - 200т.р.

Можно запускать напрямую или из Celery-задачи через функцию run_collection().
"""

import csv
import datetime as dt
import json
import sys
import time
from itertools import product
from typing import Dict, Any, Optional, List, Tuple

import requests


# === Настройки по умолчанию ===
URL = "https://api.cian.ru/search-offers-index/v2/get-meta/"
# URL = "https://kazan.cian.ru/cian-api/site/v1/offers/search/meta/"
REGION_ID = 4777  # Казань
ENGINE_VERSION = 2
BUILDING_STATUS = 1
PRICE_SM = True

ROOMS = [1, 2, 3]
PRICE_MIN = 140_000
PRICE_MAX = 220_000
PRICE_STEP = 5_000

CSV_PATH = "cian_counts.csv"
REQUEST_TIMEOUT = 15  # сек
RETRY_ATTEMPTS = 4
RETRY_BASE_SLEEP = 1.2  # секунд
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"

CSV_DELIMITER = ";"  # <--- требуемый разделитель


def price_iter(start: int, end: int, step: int):
    val = start
    while val <= end:
        yield val
        val += step


def make_column_name(room: int, price: int) -> str:
    return f"{room}к - {price // 1000}т.р."


def build_payload(room: int, price_lte: int) -> Dict[str, Any]:
    return {
        "jsonQuery": {
            "_type": "flatsale",
            "engine_version": {"type": "term", "value": ENGINE_VERSION},
            "region": {"type": "terms", "value": [REGION_ID]},
            "room": {"type": "terms", "value": [room]},
            "price": {"type": "range", "value": {"lte": price_lte}},
            "building_status": {"type": "term", "value": BUILDING_STATUS},
            "price_sm": {"type": "term", "value": PRICE_SM},
        }
    }


def fetch_count(session: requests.Session, payload: Dict[str, Any]) -> Optional[int]:

    cian_cookies(session)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        # "Origin": "https://www.cian.ru",
        "Origin": "https://kazan.cian.ru",
        # "Referer": "https://www.cian.ru/",
        "Referer": "https://kazan.cian.ru",
        "User-Agent": USER_AGENT,
    }

    last_err = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = session.post(URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return int(data["data"]["count"])
            else:
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            last_err = e

        time.sleep(RETRY_BASE_SLEEP * (2 ** (attempt - 1)))

    sys.stderr.write(f"[warn] Не удалось получить count: {last_err}\n")
    return None


def compute_columns_and_pairs(rooms: List[int], pmin: int, pmax: int, pstep: int) -> Tuple[List[str], List[Tuple[int, int]]]:
    cols = ["Дата"]
    pairs = []
    for room, price in product(rooms, price_iter(pmin, pmax, pstep)):
        col = make_column_name(room, price)
        cols.append(col)
        pairs.append((room, price))
    return cols, pairs


def ensure_header(path: str, header: list):
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=CSV_DELIMITER)
            existing = next(reader)
        if existing != header:
            raise SystemExit(
                "Структура существующего CSV не совпадает с требуемой.\n"
                f"  Существующий заголовок: {existing}\n"
                f"  Требуемый заголовок:    {header}\n"
                "Либо удалите файл, либо приведите диапазоны ROOMS/PRICE_* к тем же значениям."
            )
    except FileNotFoundError:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=CSV_DELIMITER)
            writer.writerow(header)


def run_collection(csv_path: str = CSV_PATH,
                   rooms: List[int] = None,
                   pmin: int = None,
                   pmax: int = None,
                   pstep: int = None) -> str:
    """
    Основная функция для вызова из Celery.
    Возвращает путь к CSV с добавленной строкой.
    """
    rooms = rooms or ROOMS
    pmin = pmin if pmin is not None else PRICE_MIN
    pmax = pmax if pmax is not None else PRICE_MAX
    pstep = pstep if pstep is not None else PRICE_STEP

    cols, pairs = compute_columns_and_pairs(rooms, pmin, pmax, pstep)
    ensure_header(csv_path, cols)

    today = dt.date.today().isoformat()
    row: Dict[str, Any] = {"Дата": today}

    with requests.Session() as s:
        for (room, price) in pairs:
            print(f"room={room}, price={price}")
            payload = build_payload(room, price)
            count = fetch_count(s, payload)
            row[make_column_name(room, price)] = "" if count is None else count
            time.sleep(0.15)  # вежливый rate limit

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, delimiter=CSV_DELIMITER)
        writer.writerow(row)

    return csv_path


def main():
    out_path = run_collection(CSV_PATH)
    print(f"Готово. Строка добавлена в {out_path}")


def cian_cookies(session):
    data = [
        {"name":"browser.microservice.frontend-mainpage.magazine.success","type":"counter"},
        {"name":"browser.microservice.frontend-mainpage.seoContainer.hasSeoText","type":"counter"},
        {"name":"browser.microservice.frontend-mainpage.seoContainer.hasSeoUrls","type":"counter"}
    ]
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        # "Origin": "https://www.cian.ru",
        "Origin": "https://kazan.cian.ru",
        # "Referer": "https://www.cian.ru/",
        "Referer": "https://kazan.cian.ru",
        "User-Agent": USER_AGENT,
    }
    url = "https://api.cian.ru/browser-telemetry/v1/send-stats/"
    response = session.post(url, json=data)
    cookies = response.cookies
    return response


if __name__ == "__main__":
    # res = cian_cookies()
    main()
