import os
import math
import time
import random
import re
from datetime import datetime
from urllib.parse import urldefrag

import pytz
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://www.drogueriascafam.com.co/38-nutricion"
PAGE_SIZE = 12
TZ_COL = pytz.timezone("America/Bogota")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def safe_get(url, timeout=30, tries=3, sleep_base=1.2):
    last_err = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception:
            time.sleep(sleep_base * (i + 1))
    raise last_err


def normalize_url(u: str):
    if not u:
        return None
    u, _ = urldefrag(u)
    return u.strip()


def parse_total_products(soup: BeautifulSoup):
    info = soup.select_one("div.pagination-info")
    if not info:
        return None
    txt = " ".join(info.get_text(" ", strip=True).split())
    m = re.search(r"de\s+([\d\.]+)\s+art", txt, flags=re.IGNORECASE)
    if m:
        return int(m.group(1).replace(".", ""))
    return None


def parse_price(text):
    if not text:
        return None
    t = text.replace("\xa0", " ").strip()
    t = t.replace("$", "").strip()
    return re.sub(r"\s+", " ", t)


def build_page_url(page_num: int):
    return BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"


def get_listing_scope(soup: BeautifulSoup):
    scope = soup.select_one("#js-product-list")
    if scope:
        return scope
    return soup


def parse_listing_page(page_url, page_num, extraction_ts):
    r = safe_get(page_url)
    soup = BeautifulSoup(r.text, "lxml")

    total_products = parse_total_products(soup)
    scope = get_listing_scope(soup)

    cards = scope.select("article.product-miniature, div.product-miniature")

    items = []
    for card in cards:
        a = card.select_one("h2.product-title a")
        if not a:
            continue

        items.append({
            "Nombre producto": a.get_text(" ", strip=True),
            "Laboratorio": (
                card.select_one("h6.product-brand a").get_text(" ", strip=True)
                if card.select_one("h6.product-brand a") else None
            ),
            "Precio": parse_price(
                card.select_one("span.price").get_text(" ", strip=True)
                if card.select_one("span.price") else None
            ),
            "PUM": (
                card.select_one("span.pum").get_text(" ", strip=True)
                if card.select_one("span.pum") else None
            ),
            "Página": page_num,
            "FechaHoraExtracción": extraction_ts,
            "Link producto": normalize_url(a.get("href")),
        })

    return items, total_products


def main():
    extraction_dt = datetime.now(TZ_COL)
    extraction_ts = extraction_dt.strftime("%Y-%m-%d %H:%M:%S")
    timestamp = extraction_dt.strftime("%Y-%m-%d_%H-%M-%S")

    yyyy, mm, dd = extraction_dt.strftime("%Y"), extraction_dt.strftime("%m"), extraction_dt.strftime("%d")
    out_dir = f"outputs/Nutricion/{yyyy}/{mm}/{dd}"
    os.makedirs(out_dir, exist_ok=True)

    first_items, total_products = parse_listing_page(build_page_url(1), 1, extraction_ts)
    total_pages = math.ceil(total_products / PAGE_SIZE)

    all_items = first_items[:]
    for p in range(2, total_pages + 1):
        items, _ = parse_listing_page(build_page_url(p), p, extraction_ts)
        all_items.extend(items)
        time.sleep(random.uniform(0.3, 0.8))

    df = pd.DataFrame(all_items).drop_duplicates(subset=["Link producto"])

    csv = f"{out_dir}/drogueriascafam_nutricion_{timestamp}.csv"
    xlsx = f"{out_dir}/drogueriascafam_nutricion_{timestamp}.xlsx"

    df.to_csv(csv, index=False, sep=";")
    df.to_excel(xlsx, index=False)

    print("CSV:", csv)
    print("XLSX:", xlsx)


if __name__ == "__main__":
    main()
