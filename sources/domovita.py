"""
domovita.by — раздел продажи квартир в Минске.

Как и realt.by, отдельного публичного API нет — данные встроены в HTML
внутри <script id="__NEXT_DATA__">. В отличие от realt.by, здесь реально
работают:
  - фильтр по комнатности через повторяющийся параметр rooms=2&rooms=3...;
  - постраничная навигация через параметр page=N (проверено: страницы 1 и 2
    почти не пересекаются по объявлениям).

Фильтр по цене через query-параметры не работает (проверено эмпирически),
поэтому цена фильтруется на нашей стороне. Каждое объявление уже содержит
цену, пересчитанную сайтом в USD/BYN/EUR/RUB — ручная конвертация валют не
нужна.
"""
import json
import re

import requests

from .base import Listing

BASE_URL = "https://domovita.by/minsk/flats/sale"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def fetch(rooms_values, price_max_usd, price_min_usd=0, pages=2, timeout=25):
    listings = []
    seen_ids = set()

    for page in range(1, pages + 1):
        params = [("rooms", rooms) for rooms in rooms_values]
        if page > 1:
            params.append(("page", page))

        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()

        match = NEXT_DATA_RE.search(resp.text)
        if not match:
            continue

        data = json.loads(match.group(1))
        items = (
            data.get("props", {})
            .get("pageProps", {})
            .get("listingCardsFromSSR", {})
            .get("items", [])
        )
        if not items:
            break

        for item in items:
            listing_id = item.get("id")
            if listing_id is None or listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            listing = _build_listing(item)
            if listing is not None and price_min_usd <= listing.price_usd <= price_max_usd:
                listings.append(listing)

    return listings


def fetch_one(url, timeout=25):
    """Забирает актуальные данные одного объявления по прямой ссылке —
    используется для отслеживания цены (watchlist.py). У domovita.by
    ссылка строится из человекочитаемого адреса, а не из числового id,
    поэтому (в отличие от других источников) нужен именно полный URL."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        return None
    data = json.loads(match.group(1))
    obj = data.get("props", {}).get("pageProps", {}).get("objectData")
    if not obj:
        return None
    return _build_listing(obj)


def _build_listing(item):
    price_history = item.get("price_history") or []
    price_usd = None
    if price_history:
        price_usd = (price_history[0].get("price") or {}).get("USD")

    if price_usd is None:
        return None
    try:
        price_usd = float(price_usd)
    except (TypeError, ValueError):
        return None

    url = item.get("url")
    listing_id = item.get("id")
    if not url or listing_id is None:
        return None

    area = item.get("area") or {}

    return Listing(
        source="domovita",
        listing_id=str(listing_id),
        url=url,
        title=item.get("title") or "Квартира",
        price_usd=price_usd,
        rooms=item.get("rooms"),
        area_total=area.get("total"),
        address=_format_address(item.get("address") or {}),
        created_at=item.get("date_reception"),
    )


def _format_address(address):
    town = (address.get("town") or {}).get("name") or "Минск"
    district = (address.get("district") or {}).get("name")
    street = address.get("street_name")
    house = address.get("house_number")

    street_part = " ".join(p for p in (street, house) if p)
    parts = [town, district, street_part]
    return ", ".join(p for p in parts if p)
