"""
Kufar.by — раздел недвижимости (re.kufar.by), категория "Квартиры", продажа.

Официального публичного API нет, но сайт использует внутренний JSON API,
который отдаёт чистые структурированные данные и поддерживает сортировку
по дате (sort=lst.d) и фильтр по цене (prc=r:min,max) на сервере.
Фильтр по нескольким значениям комнатности одновременно (rms=2,3) не
работает надёжно, поэтому запрашиваем каждое значение отдельно.
"""
import requests

from .base import Listing

API_URL = "https://api.kufar.by/search-api/v2/search/rendered-paginated"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

CATEGORY_APARTMENTS = 1010
REGION_MINSK = 7
LOCALITY_MINSK = "country-belarus~province-minsk~locality-minsk"


def fetch(rooms_values, price_max_usd, price_min_usd=0, limit_per_room=30, timeout=20):
    listings = []
    seen_ids = set()

    for rooms in rooms_values:
        params = {
            "cat": CATEGORY_APARTMENTS,
            "typ": "sell",
            "gtsy": LOCALITY_MINSK,
            "rgn": REGION_MINSK,
            "cur": "USD",
            "size": limit_per_room,
            "sort": "lst.d",
            "rms": rooms,
            "prc": f"r:{int(max(0, price_min_usd))},{int(price_max_usd)}",
        }
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        for ad in data.get("ads", []):
            ad_id = ad.get("ad_id")
            if ad_id is None or ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)
            listings.append(_parse_ad(ad))

    return listings


def _parse_ad(ad):
    params_by_key = {p.get("p"): p for p in ad.get("ad_parameters", []) if isinstance(p, dict)}

    rooms_raw = params_by_key.get("rooms", {}).get("v")
    rooms = _to_int(rooms_raw)

    size_raw = params_by_key.get("size", {}).get("v")
    area_total = _to_float(size_raw)

    district = params_by_key.get("re_district", {}).get("vl")
    area_name = params_by_key.get("area", {}).get("vl")
    address_parts = [p for p in (district, area_name) if p]
    address = "Минск, " + ", ".join(address_parts) if address_parts else "Минск"

    price_usd = _cents_to_amount(ad.get("price_usd"))

    ad_id = ad.get("ad_id")
    return Listing(
        source="kufar",
        listing_id=str(ad_id),
        url=ad.get("ad_link") or f"https://re.kufar.by/vi/{ad_id}",
        title=ad.get("subject") or "Квартира",
        price_usd=price_usd,
        rooms=rooms,
        area_total=area_total,
        address=address,
        created_at=ad.get("list_time"),
    )


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cents_to_amount(value):
    amount = _to_float(value)
    return amount / 100 if amount is not None else None
