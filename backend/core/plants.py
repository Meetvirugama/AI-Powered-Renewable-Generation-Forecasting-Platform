"""One place that answers "what plants exist?", for every route.

Before this, `/plants` read the `plants` table and fell back to `config/plants.yaml`,
while `/forecast`, `/dsm`, `/optimize`, `/pooling` and `/dashboard` read the YAML
directly. So a plant imported into the database appeared in the plant list and on
the map, and then returned 404 from every endpoint that would actually forecast
or price it. The inconsistency was invisible until something was written to that
table — which `scripts/import_plants.py` now does, with ~100 real Gujarat plants.

Resolution order is database first, YAML second, for both listing and lookup.
The YAML fallback is not legacy cruft: it keeps the four seed plants resolvable
by id, so the test suite and a laptop demo work with no database at all.
"""
from __future__ import annotations

import logging

from backend.core.config import load_plants_config

logger = logging.getLogger("renewable_platform")

# The keys every caller expects. A DB row and a YAML entry are normalised to the
# same shape here so no route has to know which source it got.
_FIELDS = ("id", "name", "type", "lat", "lon", "avc_mw", "pool_id")


def _from_row(row) -> dict:
    plant = {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "lat": row.lat,
        "lon": row.lon,
        "avc_mw": row.avc_mw,
        "pool_id": row.pool_id,
    }
    # Site parameters live in metadata_json for DB rows and at the top level in
    # YAML. Flattening here means feature builders and the physics gate read the
    # same keys either way.
    plant.update(row.metadata_json or {})
    return plant


def _db_plants(db) -> list[dict]:
    """Plants from the database, or [] if there are none or it is unreachable.

    Never raises: a database problem must degrade to the YAML seeds rather than
    take down every forecast endpoint.
    """
    if db is None:
        return []
    try:
        from sqlalchemy import select

        from backend.db.models import Plant

        rows = db.execute(select(Plant)).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("plants table unreadable, falling back to plants.yaml: %s", exc)
        return []
    return [_from_row(r) for r in rows]


# Sources written by scripts/import_plants.py. Their presence is what marks a
# database as holding the real inventory rather than only the seed plants.
_IMPORTED_SOURCES = frozenset({"openstreetmap", "wri_gppd"})


def list_plants(db=None) -> list[dict]:
    """Plants to *show*. Database if it has any, otherwise the YAML seeds.

    Once the real inventory is imported, the four seed plants are left out. They
    are invented -- "Gujarat Solar Plant A" has a made-up name and capacity -- and
    listing them on a map of 101 real plants presents fiction beside fact. They
    cannot simply be deleted: the daily pipeline wrote forecasts, DSM results
    and actions against them, and those rows reference the plant by foreign key.

    Hiding applies to listing only. find_plant still resolves seed ids, so
    bookmarks, tests and demo scripts naming GJ_SOLAR_A keep working, and
    plants_in_pool still sees them, so their pool keeps settling correctly.
    """
    db_plants = _db_plants(db)
    if not db_plants:
        return load_plants_config()
    if any(p.get("source") in _IMPORTED_SOURCES for p in db_plants):
        seed_ids = {p["id"] for p in load_plants_config()}
        return [p for p in db_plants if p.get("id") not in seed_ids]
    return db_plants


def find_plant(plant_id: str, db=None) -> dict | None:
    """One plant by id, checking the database first and then the YAML seeds.

    The YAML is consulted even when the database has rows, so the seed plants
    stay addressable after a real import. Otherwise importing real plants would
    silently 404 every bookmark, test and demo script that names GJ_SOLAR_A.
    """
    for plant in _db_plants(db):
        if plant.get("id") == plant_id:
            return plant
    for plant in load_plants_config():
        if plant.get("id") == plant_id:
            return plant
    return None


def plants_in_pool(pool_id: str, db=None) -> list[dict]:
    """Everything sharing a pooling station.

    Imported plants carry `pool_id = NULL` on purpose -- a CERC pooling station
    is a regulatory fact that neither OpenStreetMap nor WRI records, and pool
    membership changes the settled rupee figure. A null pool therefore matches
    nothing here rather than being treated as its own pool, which would let a
    plant be "pooled" with itself and report a saving.
    """
    if not pool_id:
        return []
    # Membership reads every plant, not list_plants: a seed plant hidden from the
    # map is still a real member of its pool for settlement.
    every_plant = _db_plants(db) or load_plants_config()
    return [p for p in every_plant if p.get("pool_id") == pool_id]
