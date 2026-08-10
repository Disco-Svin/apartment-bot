"""Ad-hoc smoke test: fetch each source and print a short summary.
Not part of the bot itself — safe to delete after manual verification."""
import yaml

from sources import domovita, kufar, onliner, realt

config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
filters = config["filters"]
rooms = filters["rooms"]
price_max = filters["price_max_usd"]
price_min = filters.get("price_min_usd", 0)
fx = filters.get("currency_per_usd", {})

print("=== kufar ===")
kufar_listings = kufar.fetch(rooms, price_max, price_min)
print(f"count={len(kufar_listings)}")
for l in kufar_listings[:3]:
    print(l)

print("\n=== onliner ===")
onliner_listings = onliner.fetch(rooms, price_max, price_min)
print(f"count={len(onliner_listings)}")
for l in onliner_listings[:3]:
    print(l)

print("\n=== realt ===")
realt_listings = realt.fetch(rooms, price_max, price_min, fx)
print(f"count={len(realt_listings)}")
for l in realt_listings[:3]:
    print(l)

print("\n=== domovita ===")
domovita_listings = domovita.fetch(rooms, price_max, price_min, pages=2)
print(f"count={len(domovita_listings)}")
for l in domovita_listings[:3]:
    print(l)

total = len(kufar_listings) + len(onliner_listings) + len(realt_listings) + len(domovita_listings)
print(f"\nTOTAL: {total}")
