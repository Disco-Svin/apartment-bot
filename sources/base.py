from dataclasses import dataclass
from typing import Optional


@dataclass
class Listing:
    source: str
    listing_id: str
    url: str
    title: str
    price_usd: Optional[float]
    rooms: Optional[int]
    area_total: Optional[float]
    address: str
    created_at: Optional[str]
