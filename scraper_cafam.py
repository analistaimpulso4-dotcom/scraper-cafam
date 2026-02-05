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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)


def safe_get(url, timeout=30, tries=4, sleep_base=1.5):
    last_err = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=timeout)
            # Si hay bloqueo temporal, reintentar con backoff
            if r.status_code in (403, 429, 503):
                last_err = RuntimeError(f"HTTP {r.status_code} al pedir {url}")
                time.sleep(sleep_base * (i + 1) + random.uniform(0.2, 0.8))
                continue

            r.raise_for_status()
            return r

        except Exception as e:
            last_err = e
            time.sleep(sleep_base * (i + 1) + random.uniform(0.2, 0.8))

    raise RuntimeError(f"No fue posible obtener la URL tras {tries} intentos: {url}. Último error: {last_err}")


def normalize_url(u: str):
    if not u:
        return None
    u, _ = urldefrag(u)  # quita fragmento #/variantes
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
    # SOLO listado principal (omite módulos como “Los más vendidos”)
    scope = soup.select_one("#js-product-list")
    return scope if scope else soup


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

        name = a.get_text(" ", strip=True)
        product_url = normalize_url(a.get("href"))

        brand_a = card.select_one("h6.product-brand a")
        laboratorio = brand_a.get_text(" ", strip=True) if brand_a else None

        price_el = card.select_one('span.price[itemprop="price"], span.price')
        price = parse_price(price_el.get_text(" ", strip=True)) if price_el else None

        pum_el = card.select_one("span.pum")
        pum = pum_el.get_text(" ", strip=True) if pum_el else None

        img = card.select_one("img")
        img_url = img.get("src") if img else None
        img_url_large = img.get("data-full-size-image-url") if img else None

        items.append({
            "Nombre producto": name,
            "Laboratorio": laboratorio,
            "Precio": price,
            "PUM": pum,
            "Página": page_num,
            "FechaHoraExtracción": extraction_ts,
            "Link producto": product_url,
            "Link imagen": img_url,
            "Link imagen grande": img_url_large,
        })

    return items, total_products


def main():
    extraction_dt = datetime.now(TZ_COL)
    extraction_ts = extraction_dt.strftime("%Y-%m-%d %H:%M:%S")
    timestamp = extraction_dt.strftime("%Y-%m-%d_%H-%M-%S")

    yyyy, mm, dd = extraction_dt.strftime("%Y"), extraction_dt.strftime("%m"), extraction_dt.strftime("%d")
    out_dir = f"outputs/Nutricion/{yyyy}/{mm}/{dd}"
    os.makedirs(out_dir, exist_ok=True)

    print("Iniciando extracción:", extraction_ts, "TZ:", TZ_COL)

    first_items, total_products = parse_listing_page(build_page_url(1), 1, extraction_ts)
    if not total_products:
        raise RuntimeError("No se pudo detectar el total de productos (div.pagination-info). Posible cambio de HTML.")

    total_pages = math.ceil(total_products / PAGE_SIZE)
    print("Total reportado por web:", total_products, "| Páginas:", total_pages)

    all_items = list(first_items)

    for p in range(2, total_pages + 1):
        items, _ = parse_listing_page(build_page_url(p), p, extraction_ts)
        all_items.extend(items)
        time.sleep(random.uniform(0.25, 0.8))

    df = pd.DataFrame(all_items)

    # Deduplicación por URL normalizada
    df = df.drop_duplicates(subset=["Link producto"], keep="first").reset_index(drop=True)

    csv = f"{out_dir}/drogueriascafam_nutricion_{timestamp}.csv"
    xlsx = f"{out_dir}/drogueriascafam_nutricion_{timestamp}.xlsx"

    df.to_csv(csv, index=False, sep=";")
    df.to_excel(xlsx, index=False)

    print("Productos únicos:", df["Link producto"].nunique())
    print("Filas DF:", len(df))
    print("Laboratorios nulos:", int(df["Laboratorio"].isna().sum()))
    print("CSV:", csv)
    print("XLSX:", xlsx)


if __name__ == "__main__":
    main()
