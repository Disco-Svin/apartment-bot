"""
realt.by — раздел продажи квартир.

У сайта нет отдельного публичного API: данные рендерятся на сервере и
встраиваются в HTML внутри тега <script id="__NEXT_DATA__">. Проверено
эмпирически, что:
  - параметр адреса (addressV2 с townUuid Минска) реально фильтрует город;
  - сегмент пути "2k"/"3k"/"4k" и параметр страницы (p=N) НЕ фильтруют и
    НЕ пагинируют результат на сервере — сайт всегда отдаёт один и тот же
    срез объявлений (около 360 штук) без сортировки по дате;
  - поэтому комнатность и цена фильтруются на нашей стороне, по всему
    полученному срезу.

Из-за отсутствия серверной сортировки по дате новые объявления могут
попасть в срез не мгновенно — этот источник даёт best-effort покрытие,
основной "радар" для действительно новых объявлений — kufar и onliner.
"""
import json
import re

import requests

from .base import Listing

SEARCH_URL = "https://realt.by/sale/flats/"
DETAIL_URL = "https://realt.by/sale-flats/object/{code}/"
TOWN_UUID_MINSK = "4cb07174-7b00-11eb-8943-0cc47adabd66"
DETAIL_URL_RE = re.compile(r"/object/(\d+)")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# ISO 4217 numeric currency codes, как их отдаёт realt.by.
CURRENCY_USD = 840
CURRENCY_BYN = 933
CURRENCY_EUR = 978
CURRENCY_RUB = 643

CURRENCY_NAME_BY_CODE = {
    CURRENCY_USD: "USD",
    CURRENCY_BYN: "BYN",
    CURRENCY_EUR: "EUR",
    CURRENCY_RUB: "RUB",
}


def fetch(rooms_values, price_max_usd, price_min_usd=0, currency_per_usd=None, timeout=25):
    currency_per_usd = currency_per_usd or {}
    params = {"addressV2": json.dumps([{"townUuid": TOWN_UUID_MINSK}])}

    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        return []

    data = json.loads(match.group(1))
    objects = data.get("props", {}).get("pageProps", {}).get("objects", [])

    rooms_set = set(rooms_values)
    listings = []

    for obj in objects:
        rooms = obj.get("rooms")
        if rooms not in rooms_set:
            continue

        listing = _build_listing(obj, currency_per_usd)
        if listing is None:
            continue
        if not (price_min_usd <= listing.price_usd <= price_max_usd):
            continue

        listings.append(listing)

    return listings


def fetch_one(url_or_code, currency_per_usd=None, timeout=25):
    """Забирает актуальные данные одного объявления по ссылке или code —
    используется для отслеживания цены (watchlist.py). Страница
    объявления встраивает тот же JSON, что и страница поиска."""
    code = str(url_or_code)
    if not code.isdigit():
        match = DETAIL_URL_RE.search(code)
        if not match:
            return None
        code = match.group(1)

    resp = requests.get(DETAIL_URL.format(code=code), headers=HEADERS, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        return None
    data = json.loads(match.group(1))
    obj = data.get("props", {}).get("pageProps", {}).get("object")
    if not obj:
        return None
    return _build_listing(obj, currency_per_usd or {})


def _build_listing(obj, currency_per_usd):
    price_usd = _to_usd(obj.get("price"), obj.get("priceCurrency"), currency_per_usd)
    if price_usd is None:
        return None

    code = obj.get("code")
    if code is None:
        return None

    rooms = obj.get("rooms")
    return Listing(
        source="realt",
        listing_id=str(code),
        url=DETAIL_URL.format(code=code),
        title=obj.get("title") or f"{rooms}-комн. квартира",
        price_usd=price_usd,
        rooms=rooms,
        area_total=obj.get("areaTotal"),
        address=obj.get("address") or "Минск",
        created_at=obj.get("createdAt"),
    )


def _to_usd(price, currency_code, currency_per_usd):
    if price is None:
        return None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None

    if currency_code == CURRENCY_USD:
        return price

    currency_name = CURRENCY_NAME_BY_CODE.get(currency_code)
    rate = currency_per_usd.get(currency_name) if currency_name else None
    if not rate:
        return None
    return price / rate
