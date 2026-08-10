"""Ad-hoc smoke test: fetch each source and print a short summary.
Not part of the bot itself — safe to delete after manual verification."""
import yaml

from sources import domovita, gohome, kufar, onliner, realt, t_s

config = yaml.safe_load(open("config.yaml", encoding="utf-8"))
filters = config["filters"]
rooms = filters["rooms"]
price_max = filters["price_max_usd"]
price_min = filters.get("price_min_usd", 0)
fx = filters.get("currency_per_usd", {})

results = {}

print("=== kufar ===")
results["kufar"] = kufar.fetch(rooms, price_max, price_min)
print(f"count={len(results['kufar'])}")
for l in results["kufar"][:3]:
    print(l)

print("\n=== onliner ===")
results["onliner"] = onliner.fetch(rooms, price_max, price_min)
print(f"count={len(results['onliner'])}")
for l in results["onliner"][:3]:
    print(l)

print("\n=== realt ===")
results["realt"] = realt.fetch(rooms, price_max, price_min, fx)
print(f"count={len(results['realt'])}")
for l in results["realt"][:3]:
    print(l)

print("\n=== domovita ===")
results["domovita"] = domovita.fetch(rooms, price_max, price_min, pages=2)
print(f"count={len(results['domovita'])}")
for l in results["domovita"][:3]:
    print(l)

print("\n=== gohome ===")
results["gohome"] = gohome.fetch(rooms, price_max, price_min, fx)
print(f"count={len(results['gohome'])}")
for l in results["gohome"][:3]:
    print(l)

print("\n=== t_s ===")
results["t_s"] = t_s.fetch(rooms, price_max, price_min, fx)
print(f"count={len(results['t_s'])}")
for l in results["t_s"][:3]:
    print(l)

total = sum(len(v) for v in results.values())
print(f"\nTOTAL: {total}")
