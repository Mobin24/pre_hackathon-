"""Populate the `resources` collection with dummy relief assets.

This gives the matching engine + admin dashboard something real to score
against for demos. It is intentionally synthetic (no real orgs / phones);
the `contact.phone` field uses clearly-fake placeholder numbers.

Usage (run from `backend/` with the virtualenv active):

    python -m scripts.seed_resources            # default: ~120 resources
    python -m scripts.seed_resources --reset    # wipe + reseed
    python -m scripts.seed_resources --count 50 # custom size

Idempotent: by default it adds to the existing collection. Pass `--reset`
to clear out docs that came from a previous seed (matched by the
`SEED_PREFIX` on the `code` field).
"""
import argparse
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Make `app.*` importable when invoked as `python -m scripts.seed_resources`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402
from app.models import resource as resource_model  # noqa: E402

SEED_PREFIX = "SEED"

# 8 Bangladesh divisions, each with one major city + lat/lng. Numbers are
# approximate centroids — good enough for a demo, not for ops.
DIVISIONS: List[Dict[str, Any]] = [
    {"division": "Dhaka",     "district": "Dhaka",     "area": "Ramna",         "lat": 23.7280, "lng": 90.3970},
    {"division": "Chattogram","district": "Chattogram","area": "Kotwali",       "lat": 22.3330, "lng": 91.8123},
    {"division": "Khulna",    "district": "Khulna",    "area": "Sonadanga",     "lat": 22.8270, "lng": 89.5380},
    {"division": "Rajshahi",  "district": "Rajshahi",  "area": "Boalia",        "lat": 24.3636, "lng": 88.6241},
    {"division": "Rangpur",   "district": "Rangpur",   "area": "Rangpur Sadar", "lat": 25.7460, "lng": 89.2750},
    {"division": "Barishal",  "district": "Barishal",  "area": "Barishal Sadar","lat": 22.7010, "lng": 90.3535},
    {"division": "Sylhet",    "district": "Sylhet",    "area": "Sylhet Sadar",  "lat": 24.8949, "lng": 91.8687},
    {"division": "Mymensingh","district": "Mymensingh","area": "Mymensingh Sadar","lat": 24.7471, "lng": 90.4203},
]

# Resources per type, in priority order — those near the top are more
# common in real disasters so the seed mirrors that.
TYPE_TEMPLATES: List[Dict[str, Any]] = [
    {"type": "volunteer",     "capacity_range": (1, 1),  "assistance": ["rescue_team"],            "skill_pool": ["first_aid", "swim_rescue", "trauma", "icu", "search"]},
    {"type": "ambulance",     "capacity_range": (1, 4),  "assistance": ["ambulance", "medicine"],   "skill_pool": []},
    {"type": "rescue_boat",   "capacity_range": (4, 12), "assistance": ["rescue_boat", "rescue_team"], "skill_pool": []},
    {"type": "rescue_team",   "capacity_range": (6, 14), "assistance": ["rescue_team"],            "skill_pool": []},
    {"type": "shelter",       "capacity_range": (50, 200), "assistance": ["shelter"],             "skill_pool": []},
    {"type": "medical_team",  "capacity_range": (2, 6),  "assistance": ["medical", "medicine"],    "skill_pool": ["trauma", "icu", "obstetrics", "general"]},
    {"type": "food_depot",    "capacity_range": (200, 1000), "assistance": ["food"],             "skill_pool": []},
    {"type": "water_point",   "capacity_range": (500, 5000), "assistance": ["water"],            "skill_pool": []},
    {"type": "medicine_store","capacity_range": (100, 800), "assistance": ["medicine"],          "skill_pool": []},
    {"type": "clothes_depot", "capacity_range": (100, 600), "assistance": ["clothes"],          "skill_pool": []},
    {"type": "baby_supplies", "capacity_range": (50, 200),  "assistance": ["baby_supplies"],    "skill_pool": []},
    {"type": "other",         "capacity_range": (1, 1),     "assistance": ["other"],             "skill_pool": []},
]


def _build_doc(idx: int, template: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    div = rng.choice(DIVISIONS)
    type_ = template["type"]
    capacity_min, capacity_max = template["capacity_range"]
    capacity = rng.randint(capacity_min, capacity_max)
    code = f"{SEED_PREFIX}-{type_.upper()}-{div['division'][:3].upper()}-{idx:03d}"
    # Nudge the coords a few km around the centroid so we have spread.
    lat = div["lat"] + rng.uniform(-0.05, 0.05)
    lng = div["lng"] + rng.uniform(-0.05, 0.05)
    is_shelter = type_ == "shelter"
    skills = (
        rng.sample(template["skill_pool"], k=min(len(template["skill_pool"]), rng.randint(1, 3)))
        if template["skill_pool"] else []
    )
    return {
        "code": code,
        "type": type_,
        "name": f"{type_.replace('_', ' ').title()} #{idx:03d} — {div['area']}",
        "assistance": template["assistance"],
        "skills": skills,
        "location": {
            "division": div["division"],
            "district": div["district"],
            "area": div["area"],
            "coords": {"lat": round(lat, 5), "lng": round(lng, 5)},
        },
        "capacity": 1 if is_shelter else capacity // 50 if type_ == "volunteer" else 1,
        "capacity_total": capacity if is_shelter else None,
        "capacity_used": rng.randint(0, capacity // 4) if is_shelter else None,
        "available": rng.random() > 0.15,  # ~85% available
        "contact": {
            "name": f"Focal {div['division']} #{idx:03d}",
            "phone": f"+88017{rng.randint(10_000_000, 99_999_999)}",
        },
        "priority": rng.choice([0, 0, 0, 1, 2]),
        "tags": ["24x7"] if rng.random() > 0.6 else [],
    }


async def reset_seed() -> int:
    db = get_database()
    res = await db[resource_model.COLLECTION].delete_many(
        {"code": {"$regex": f"^{SEED_PREFIX}-"}}
    )
    return res.deleted_count


async def seed(n: int, reset: bool) -> Dict[str, int]:
    rng = random.Random(2026_07_03)  # deterministic seed for repeatability
    db = get_database()
    if reset:
        deleted = await reset_seed()
        print(f"  ↻ wiped {deleted} previously-seeded resources")
    now = datetime.now(timezone.utc)
    per_type = max(1, n // len(TYPE_TEMPLATES))
    docs: List[Dict[str, Any]] = []
    idx = 1
    for template in TYPE_TEMPLATES:
        for _ in range(per_type):
            docs.append({**_build_doc(idx, template, rng), "created_at": now, "updated_at": now})
            idx += 1
    if docs:
        await db[resource_model.COLLECTION].insert_many(docs)
    return {"inserted": len(docs)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo resources.")
    parser.add_argument(
        "--count", type=int, default=120,
        help="Total resources to seed (split across types). Default 120.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete previously-seeded docs (matched by SEED prefix) before inserting.",
    )
    return parser.parse_args(argv)


async def main_async() -> None:
    args = parse_args()
    if args.count < len(TYPE_TEMPLATES):
        sys.exit(f"--count must be at least {len(TYPE_TEMPLATES)} to cover all types.")
    try:
        await connect_to_mongo()
        result = await seed(args.count, args.reset)
        print(f"  ✓ inserted {result['inserted']} resources (request: {args.count})")
    finally:
        await close_mongo_connection()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()