"""
r.onliner.by — сервис "Купить квартиру" от Onliner (не путать с ab.onliner.by,
это автобарахолка). Отдаёт чистый JSON API с фильтрами по цене, комнатности
и сортировкой по дате создания на сервере — самый удобный из четырёх
источников.
"""
import requests

from .base import Listing

API_URL = "https://r.onliner.by/sdapi/pk.api/search/apartments"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

# Примерный bounding box города Минска.
MINSK_BOUNDS = {
    "lb_lat": 53.80,
    "lb_long": 27.35,
    "rt_lat": 53.99,
    "rt_long": 27.77,
}


def fetch(rooms_values, price_max_usd, price_min_usd=0, limit=50, timeout=20):
    params = [
        ("bounds[lb][lat]", MINSK_BOUNDS["lb_lat"]),
        ("bounds[lb][long]", MINSK_BOUNDS["lb_long"]),
        ("bounds[rt][lat]", MINSK_BOUNDS["rt_lat"]),
        ("bounds[rt][long]", MINSK_BOUNDS["rt_long"]),
        ("price[min]", max(1, int(price_min_usd))),
        ("price[max]", int(price_max_usd)),
        ("currency", "usd"),
        ("order", "created_at:desc"),
        ("limit", limit),
        ("page", 1),
    ]
    for rooms in rooms_values:
        params.append(("number_of_rooms[]", rooms))

    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    listings = []
    for apartment in data.get("apartments", []):
        listing = _parse_apartment(apartment)
        if listing is not None:
            listings.append(listing)
    return listings


def _parse_apartment(a):
    apartment_id = a.get("id")
    url = a.get("url")
    if apartment_id is None or not url:
        return None

    price_usd = None
    price = a.get("price") or {}
    converted = price.get("converted") or {}
    usd_block = converted.get("USD") or {}
    if usd_block.get("amount") is not None:
        try:
            price_usd = float(usd_block["amount"])
        except (TypeError, ValueError):
            price_usd = None

    area = a.get("area") or {}
    rooms = a.get("number_of_rooms")
    area_total = area.get("total")

    title = f"{rooms}-комн. квартира, {area_total} м²" if rooms and area_total else "Квартира"
    address = (a.get("location") or {}).get("address") or "Минск"

    return Listing(
        source="onliner",
        listing_id=str(apartment_id),
        url=url,
        title=title,
        price_usd=price_usd,
        rooms=rooms,
        area_total=area_total,
        address=address,
        created_at=a.get("created_at"),
    )
