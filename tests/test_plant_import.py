"""Importing real plants, and resolving them consistently across every route.

Two things these cover, both of which produce wrong money rather than an error:

1. A capacity that was guessed rather than read. OSM tags capacity as free text
   and often as the literal string `yes`. A guessed MW becomes a guessed
   forecast and then a guessed DSM penalty, so an unparseable capacity must drop
   the plant rather than default it.
2. A plant that exists in one place and not another. `/plants` read the database
   while `/forecast` read the YAML, so an imported plant appeared on the map and
   404'd when you clicked it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("import_plants", ROOT / "scripts" / "import_plants.py")
import_plants = importlib.util.module_from_spec(_spec)
sys.modules["import_plants"] = import_plants
_spec.loader.exec_module(import_plants)

from backend.core import plants as plant_resolver  # noqa: E402


def _osm(osm_id: int, source: str, capacity: str | None, lat=23.0, lon=71.0, name=None) -> dict:
    tags = {"power": "plant", "plant:source": source}
    if capacity is not None:
        tags["plant:output:electricity"] = capacity
    if name:
        tags["name"] = name
    return {"type": "way", "id": osm_id, "center": {"lat": lat, "lon": lon}, "tags": tags}


# ------------------------------------------------------------ capacity parsing
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("25 MW", 25.0),
        ("1.5 MW", 1.5),
        ("500 kW", 0.5),
        ("1 GW", 1000.0),
        ("1,000 MW", 1000.0),
        ("40", 40.0),      # bare number: OSM's documented unit is MW
    ],
)
def test_capacity_strings_parse_to_megawatts(raw, expected):
    assert import_plants.parse_capacity_mw(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["yes", "", None, "unknown", "lots"])
def test_an_unreadable_capacity_is_none_not_a_default(raw):
    """`yes` means "a plant is here and nobody recorded its size". Defaulting it
    would put an invented MW figure into the DSM engine, which prices whatever
    it is handed."""
    assert import_plants.parse_capacity_mw(raw) is None


def test_a_plant_with_no_usable_capacity_is_dropped_and_counted():
    elements = [_osm(1, "solar", "25 MW"), _osm(2, "solar", "yes"), _osm(3, "wind", None)]
    plants, skipped = import_plants.to_plants(elements, min_mw=1.0)
    assert len(plants) == 1
    assert skipped["no_capacity"] == 2


def test_rooftop_scale_plants_are_excluded():
    """Below a megawatt this is not something a grid operator schedules, and the
    DSM tolerance band becomes meaninglessly small."""
    plants, skipped = import_plants.to_plants([_osm(1, "solar", "200 kW")], min_mw=1.0)
    assert plants == []
    assert skipped["below_min"] == 1


def test_non_renewable_and_unlocated_elements_are_skipped():
    coal = {"type": "way", "id": 9, "center": {"lat": 23.0, "lon": 71.0},
            "tags": {"power": "plant", "plant:source": "coal"}}
    nowhere = {"type": "way", "id": 10,
               "tags": {"power": "plant", "plant:source": "solar",
                        "plant:output:electricity": "10 MW"}}
    plants, skipped = import_plants.to_plants([coal, nowhere], min_mw=1.0)
    assert plants == []
    assert skipped["no_source"] == 1 and skipped["no_location"] == 1


def test_plant_ids_are_stable_so_reimporting_updates_rather_than_duplicates():
    first, _ = import_plants.to_plants([_osm(4242, "solar", "25 MW")], min_mw=1.0)
    second, _ = import_plants.to_plants([_osm(4242, "solar", "30 MW")], min_mw=1.0)
    assert first[0]["id"] == second[0]["id"] == "OSM_W4242"


def test_every_imported_plant_carries_its_attribution():
    plants, _ = import_plants.to_plants([_osm(1, "solar", "25 MW")], min_mw=1.0)
    assert "OpenStreetMap" in plants[0]["metadata_json"]["attribution"]


def test_imported_plants_have_no_pool_by_default():
    """A CERC pooling station is a regulatory fact that OSM does not record, and
    pool membership changes the settled rupee figure."""
    plants, _ = import_plants.to_plants([_osm(1, "solar", "25 MW")], min_mw=1.0)
    assert plants[0]["pool_id"] is None


def test_clustered_pools_are_labelled_as_an_assumption():
    plants, _ = import_plants.to_plants(
        [_osm(1, "solar", "25 MW", lat=23.1, lon=71.1), _osm(2, "solar", "30 MW", lat=23.2, lon=71.2)],
        min_mw=1.0,
    )
    import_plants.cluster_pools(plants)
    assert plants[0]["pool_id"] == plants[1]["pool_id"]
    assert "assumed" in plants[0]["metadata_json"]["pool_assignment"]


# ------------------------------------------------------------------- de-duping
def test_the_same_site_in_both_databases_is_imported_once():
    """"Charanka solar park" and "Charanka Solar Power Plant" are one site.
    Without de-duplication the map shows it twice and portfolio MW double-counts."""
    osm, _ = import_plants.to_plants([_osm(1, "solar", "615 MW", lat=23.906, lon=71.206)], min_mw=1.0)
    gppd = [{"id": "GPPD_X", "name": "Charanka Solar Power Plant", "type": "solar",
             "lat": 23.907, "lon": 71.188, "avc_mw": 221.0, "pool_id": None,
             "metadata_json": {"source": "wri_gppd"}}]
    merged = import_plants.merge_sources(osm, gppd)
    assert len(merged) == 1
    assert merged[0]["metadata_json"]["source"] == "openstreetmap"


def test_genuinely_separate_nearby_plants_are_both_kept():
    osm, _ = import_plants.to_plants([_osm(1, "solar", "25 MW", lat=23.0, lon=71.0)], min_mw=1.0)
    far = [{"id": "GPPD_Y", "name": "Elsewhere", "type": "solar", "lat": 23.5, "lon": 71.5,
            "avc_mw": 40.0, "pool_id": None, "metadata_json": {"source": "wri_gppd"}}]
    assert len(import_plants.merge_sources(osm, far)) == 2


def test_a_wind_farm_is_not_deduped_against_a_solar_plant_at_the_same_site():
    osm, _ = import_plants.to_plants([_osm(1, "solar", "25 MW", lat=23.0, lon=71.0)], min_mw=1.0)
    wind = [{"id": "GPPD_Z", "name": "Co-located wind", "type": "wind", "lat": 23.0, "lon": 71.0,
             "avc_mw": 40.0, "pool_id": None, "metadata_json": {"source": "wri_gppd"}}]
    assert len(import_plants.merge_sources(osm, wind)) == 2


# ---------------------------------------------------------- boundary filtering
def _square(west, south, east, north):
    return [[(west, south), (east, south), (east, north), (west, north), (west, south)]]


def test_a_plant_outside_the_state_boundary_is_dropped():
    """Gujarat's bounding box reaches longitude 74.6, which at southern latitudes
    is inside Maharashtra -- Sakri and Brahmanvel were being imported as Gujarat
    assets on that basis."""
    rings = _square(68.0, 20.0, 73.0, 24.0)
    inside, outside = import_plants.within_boundary(
        [
            {"name": "In Gujarat", "lat": 23.0, "lon": 71.0},
            {"name": "Sakri, Maharashtra", "lat": 21.07, "lon": 74.39},
        ],
        rings,
    )
    assert [p["name"] for p in inside] == ["In Gujarat"]
    assert [p["name"] for p in outside] == ["Sakri, Maharashtra"]


def test_point_in_polygon_handles_a_concave_shape():
    """States are not rectangles; Gujarat has a deeply concave coastline."""
    c_shape = [[(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10), (0, 0)]]
    assert import_plants._in_ring(5, 1, c_shape[0]) is True     # in the base
    assert import_plants._in_ring(5, 6, c_shape[0]) is False    # in the notch


# ------------------------------------------------------- the shared plant lookup
class _Row:
    def __init__(self, **kw):
        self.metadata_json = kw.pop("metadata_json", {})
        for k, v in kw.items():
            setattr(self, k, v)


class _DB:
    """Minimal stand-in for a session: only `execute(...).scalars().all()`."""

    def __init__(self, rows, raises=False):
        self._rows, self._raises = rows, raises

    def execute(self, *_a, **_k):
        if self._raises:
            raise RuntimeError("database is down")
        outer = self

        class _R:
            def scalars(self):
                class _S:
                    def all(self_inner):
                        return outer._rows
                return _S()
        return _R()


def _row(pid="OSM_W1", pool=None):
    return _Row(id=pid, name="Real Plant", type="solar", lat=23.0, lon=71.0,
                avc_mw=50.0, pool_id=pool, metadata_json={"source": "openstreetmap"})


def test_the_database_is_preferred_when_it_has_plants():
    listed = plant_resolver.list_plants(_DB([_row()]))
    assert [p["id"] for p in listed] == ["OSM_W1"]


def test_the_yaml_seeds_are_used_when_the_database_is_empty():
    """A laptop demo and the test suite must work with no database at all."""
    listed = plant_resolver.list_plants(_DB([]))
    assert listed and any(p["id"] == "GJ_SOLAR_A" for p in listed)


def test_a_database_failure_degrades_to_the_seeds_rather_than_500ing():
    listed = plant_resolver.list_plants(_DB([], raises=True))
    assert listed and any(p["id"] == "GJ_SOLAR_A" for p in listed)


def test_seed_plants_stay_addressable_after_a_real_import():
    """Otherwise importing real plants silently 404s every bookmark, test and
    demo script that names GJ_SOLAR_A."""
    assert plant_resolver.find_plant("GJ_SOLAR_A", _DB([_row()]))["id"] == "GJ_SOLAR_A"


def test_an_imported_plant_is_found_by_id():
    assert plant_resolver.find_plant("OSM_W1", _DB([_row()]))["avc_mw"] == 50.0


def test_an_unknown_plant_is_none_not_an_invented_default():
    assert plant_resolver.find_plant("NO_SUCH_PLANT", _DB([_row()])) is None


def test_site_parameters_in_metadata_are_flattened_for_the_feature_builder():
    row = _Row(id="OSM_W2", name="X", type="solar", lat=23.0, lon=71.0, avc_mw=10.0,
               pool_id=None, metadata_json={"tilt_deg": 22.0, "source": "openstreetmap"})
    assert plant_resolver.find_plant("OSM_W2", _DB([row]))["tilt_deg"] == 22.0


def test_a_null_pool_matches_nothing_rather_than_pooling_with_itself():
    """A plant pooled with itself reports a saving against its own deviation,
    which is a number that should never reach the dashboard."""
    assert plant_resolver.plants_in_pool(None, _DB([_row(pool=None)])) == []
    assert plant_resolver.plants_in_pool("", _DB([_row(pool=None)])) == []


def test_plants_are_grouped_by_their_declared_pool():
    db = _DB([_row("OSM_W1", pool="P1"), _row("OSM_W2", pool="P1"), _row("OSM_W3", pool="P2")])
    assert len(plant_resolver.plants_in_pool("P1", db)) == 2


# ----------------------------------------------------------- hiding the seed plants
def _seed_row(pid="GJ_SOLAR_A", pool="GJ_POOL_1"):
    """A seed plant as it exists on the live database: written by the pipeline,
    so it carries no import `source`."""
    return _Row(id=pid, name="Gujarat Solar Plant A", type="solar", lat=23.2, lon=72.6,
                avc_mw=50.0, pool_id=pool, metadata_json={})


def test_seed_plants_are_hidden_from_the_list_once_real_plants_are_imported():
    """Four invented plants were listed beside 101 real ones on the map."""
    db = _DB([_seed_row(), _row("OSM_W1")])
    assert [p["id"] for p in plant_resolver.list_plants(db)] == ["OSM_W1"]


def test_seed_plants_are_listed_when_nothing_real_has_been_imported():
    """A database holding only the pipeline's seed rows must still show them;
    otherwise a fresh deployment would list nothing at all."""
    db = _DB([_seed_row()])
    assert [p["id"] for p in plant_resolver.list_plants(db)] == ["GJ_SOLAR_A"]


def test_a_hidden_seed_plant_still_resolves_by_id():
    """Pipeline history, bookmarks and tests reference GJ_SOLAR_A directly."""
    db = _DB([_seed_row(), _row("OSM_W1")])
    assert plant_resolver.find_plant("GJ_SOLAR_A", db)["id"] == "GJ_SOLAR_A"


def test_hiding_a_seed_plant_does_not_remove_it_from_its_pool():
    """Pool membership decides the settled rupee figure. A plant hidden from the
    map is still connected to its pooling station."""
    db = _DB([_seed_row(), _seed_row("GJ_SOLAR_B"), _row("OSM_W1")])
    members = {p["id"] for p in plant_resolver.plants_in_pool("GJ_POOL_1", db)}
    assert members == {"GJ_SOLAR_A", "GJ_SOLAR_B"}


def test_clustered_pools_never_mix_solar_and_wind():
    """A mixed proximity pool reported a 100% saving: near-idle wind capacity
    widened the pooled tolerance band enough to absorb the solar plants'
    deviations. Pools this script invents stay within one technology."""
    plants, _ = import_plants.to_plants(
        [_osm(1, "solar", "25 MW", lat=23.1, lon=71.1), _osm(2, "wind", "30 MW", lat=23.2, lon=71.2)],
        min_mw=1.0,
    )
    import_plants.cluster_pools(plants)
    solar, wind = sorted(plants, key=lambda p: p["type"])
    assert solar["pool_id"] != wind["pool_id"]
    assert "SOLAR" in solar["pool_id"] and "WIND" in wind["pool_id"]
