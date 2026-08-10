"""
gohome.by — раздел продажи квартир.

Обычный серверный HTML, без embedded JSON. Фильтр по комнатам/цене и
сортировка "сначала обновлённые" реально работают через query-параметры
(search[room][]=2&search[cost_to]=100000&search[sort_field]=date_last_up_desc)
— проверено эмпирически. А вот постраничная навигация вместе с этими же
фильтрами отдаёт почти тот же набор объявлений, что и первая страница
(похоже на особенность/баг самого сайта) — поэтому берём только первую
страницу (~50 карточек), покрытие best-effort, как и у realt.by.

Раздел "minsk" на сайте включает не только сам город, но и соседние
агрогородки/посёлки Минского района — отсекаем их по префиксу адреса
"г. Минск". В списке показывается только цена в BYN — переводим в USD
по курсу из конфига. Даты создания в списке нет, только "Дата
обновления" — created_at не заполняем, "новое" определяем по id.
"""
import re

import requests
from bs4 import BeautifulSoup

from .base import Listing

SEARCH_URL = "https://gohome.by/sale/flat/minsk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

ROOMS_RE = re.compile(r"(\d+)-комнатная")
AREA_RE = re.compile(r"([\d.]+)\s*/\s*[\d.]+\s*/\s*[\d.]+\s*м")


def fetch(rooms_values, price_max_usd, price_min_usd=0, currency_per_usd=None, timeout=25):
    currency_per_usd = currency_per_usd or {}
    params = [
        ("search[sort_field]", "date_last_up_desc"),
        ("search[cost_to]", int(price_max_usd)),
    ]
    for rooms in rooms_values:
        params.append(("search[room][]", rooms))

    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    listings = []
    for card in soup.select(".w-object-list-item[data-object-id]"):
        listing = _parse_card(card, currency_per_usd)
        if listing is None:
            continue
        if not (price_min_usd <= listing.price_usd <= price_max_usd):
            continue
        listings.append(listing)
    return listings


def _parse_card(card, currency_per_usd):
    object_id = card.get("data-object-id")
    if not object_id:
        return None

    name_link = card.select_one(".name__link")
    if not name_link:
        return None
    title = name_link.get_text(strip=True)

    address_el = card.select_one(".w-adress .text .col-sm-auto")
    address = address_el.get_text(" ", strip=True) if address_el else title
    if "г. Минск" not in address and "г.Минск" not in address:
        return None  # пригород/агрогородок Минского района, а не сам город

    square_area_el = card.select_one(".w-square-area")
    square_area_text = square_area_el.get_text(" ", strip=True) if square_area_el else ""
    rooms_match = ROOMS_RE.search(square_area_text) or ROOMS_RE.search(title)
    rooms = int(rooms_match.group(1)) if rooms_match else None
    area_match = AREA_RE.search(square_area_text)
    area_total = float(area_match.group(1)) if area_match else None

    price_el = card.select_one(".price.primary")
    price_usd = None
    if price_el:
        price_text = price_el.get_text(" ", strip=True)
        if "руб" in price_text:
            digits = re.sub(r"\D", "", price_text.split("руб")[0])
            if digits:
                rate = currency_per_usd.get("BYN")
                if rate:
                    price_usd = float(digits) / rate

    if price_usd is None:
        return None

    return Listing(
        source="gohome",
        listing_id=str(object_id),
        url=f"https://gohome.by/ads/view/{object_id}",
        title=title,
        price_usd=price_usd,
        rooms=rooms,
        area_total=area_total,
        address=address,
        created_at=None,
    )
