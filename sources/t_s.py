"""
t-s.by (Твоя Столица) — раздел продажи квартир.

Сайт на Bitrix, фильтр по параметрам через query-строку использует
захешированные имена полей (arrFilter_695_...), но у сайта есть чистый
человекочитаемый вариант того же фильтра:
    /buy/flats/filter/rooms-is-{комнаты}/price-to-{цена в BYN}/
— проверено эмпирически, отдаёт тот же результат. Комбинировать
несколько значений комнатности в одном сегменте (например "2.3.4")
не получилось — сайт отбрасывает фильтр целиком, поэтому запрашиваем
каждое значение комнатности отдельно, как и для kufar.

Надёжной сортировки/пагинации по дате не нашлось, поэтому берём один
доступный срез по каждой комнатности — best-effort покрытие, как у
realt.by. Зато цена в USD у каждой карточки уже готова (.card-item__usd-price)
— конвертация валют не нужна.
"""
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Listing

BASE_URL = "https://www.t-s.by"
FILTER_URL_TMPL = BASE_URL + "/buy/flats/filter/rooms-is-{rooms}/price-to-{price_byn}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

ROOMS_RE = re.compile(r"(\d+)-комнатная")
AREA_RE = re.compile(r"([\d.]+)\s*/\s*[\d.]+\s*/\s*[\d.]+\s*м")
USD_RE = re.compile(r"([\d\s]+)\s*USD")


def fetch(rooms_values, price_max_usd, price_min_usd=0, currency_per_usd=None, timeout=25):
    currency_per_usd = currency_per_usd or {}
    byn_rate = currency_per_usd.get("BYN")
    price_byn = int(price_max_usd * byn_rate) if byn_rate else int(price_max_usd * 3.3)

    listings = []
    seen_ids = set()

    for i, rooms in enumerate(rooms_values):
        if i > 0:
            time.sleep(0.5)  # не долбим сайт подряд, чтобы не словить анти-бот блокировку
        url = FILTER_URL_TMPL.format(rooms=rooms, price_byn=price_byn)
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select(".card-item.paginator-item"):
            listing = _parse_card(card)
            if listing is None or listing.listing_id in seen_ids:
                continue
            if not (price_min_usd <= listing.price_usd <= price_max_usd):
                continue
            seen_ids.add(listing.listing_id)
            listings.append(listing)

    return listings


URL_ID_RE = re.compile(r"-(\d+)/?$")


def _parse_card(card):
    link_el = card.select_one("a.card-item__link")
    href = link_el.get("href") if link_el else None
    if not href:
        return None
    url = href if href.startswith("http") else BASE_URL + href

    object_id = None
    input_el = card.select_one("input[data-id_obj]")
    if input_el:
        object_id = input_el.get("data-id_obj")
    if not object_id:
        match = URL_ID_RE.search(href)
        object_id = match.group(1) if match else None
    if not object_id:
        return None

    header_el = card.select_one(".card-item__header")
    header_text = header_el.get_text(" ", strip=True) if header_el else ""
    if "Минск" not in header_text:
        return None  # другой город (t-s.by продаёт квартиры по всей Беларуси)

    rooms_match = ROOMS_RE.search(header_text)
    rooms = int(rooms_match.group(1)) if rooms_match else None
    title = header_text or (input_el.get("data-title") if input_el else None) or "Квартира"

    location_el = card.select_one(".card-item__location")
    location = location_el.get_text(" ", strip=True) if location_el else ""
    address_part = header_text.split("квартира", 1)[-1].strip(" ,") or header_text
    address = ", ".join(p for p in (address_part, location) if p)

    params_el = card.select_one(".card-item__params")
    params_text = params_el.get_text(" ", strip=True) if params_el else ""
    area_match = AREA_RE.search(params_text)
    area_total = float(area_match.group(1)) if area_match else None

    price_usd = None
    usd_price_el = card.select_one(".card-item__usd-price")
    if usd_price_el:
        match = USD_RE.search(usd_price_el.get_text(" ", strip=True))
        if match:
            price_usd = float(match.group(1).replace(" ", "").replace("\xa0", ""))
    if price_usd is None and input_el:
        raw_usd = input_el.get("data-priceusd") or input_el.get("data-priceUsd")
        if raw_usd:
            digits = re.sub(r"\D", "", raw_usd)
            if digits:
                price_usd = float(digits)

    if price_usd is None:
        return None

    return Listing(
        source="t_s",
        listing_id=str(object_id),
        url=url,
        title=title,
        price_usd=price_usd,
        rooms=rooms,
        area_total=area_total,
        address=address,
        created_at=None,
    )
