#!/usr/bin/env python3
"""Refresh data/interchange.json from The Hideout's public data.

Sources (both community data by The Hideout, CC BY-NC-SA 4.0):
  * Marker positions: tarkov.dev GraphQL API, https://api.tarkov.dev/graphql
    (the same data behind the `maps` query on tarkov.dev).
  * Map config (game->SVG transform, bounds, floor height extents, area
    labels): src/data/maps.json in https://github.com/the-hideout/tarkov-dev

The transform replicates tarkov.dev's own map page math
(src/pages/map/index.jsx in the same repo): a marker's latLng is
(lat = position.z, lng = position.x), the projection rotates it by the
map's coordinateRotation (180 degrees for Interchange), then a Leaflet
Transformation(scaleX, marginX, -scaleZ, marginY) is applied. The SVG
basemap is overlaid exactly on the map bounds, so projected coordinates
are finally normalised into the SVG viewBox.

Usage:  python3 scripts/fetch_data.py [--attempts N] [--delay SECONDS]
On failure (e.g. the API is down) the existing snapshot is left untouched.
"""

import argparse
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.tarkov.dev/graphql"
MAPS_JSON_URL = (
    "https://raw.githubusercontent.com/the-hideout/tarkov-dev/main/src/data/maps.json"
)
SVG_PATH = ROOT / "assets" / "Interchange.svg"
OUT_PATH = ROOT / "data" / "interchange.json"

QUERY = """
{
  maps(name: "Interchange") {
    name
    normalizedName
    extracts {
      id
      name
      faction
      top
      bottom
      position { x y z }
      switches { id name }
      transferItem { count item { name normalizedName } }
    }
    transits {
      id
      description
      conditions
      top
      bottom
      position { x y z }
      map { name normalizedName }
    }
    spawns {
      zoneName
      sides
      categories
      position { x y z }
    }
    bosses {
      spawnChance
      boss { name normalizedName }
      spawnLocations { spawnKey name chance }
    }
    locks {
      lockType
      needsPower
      position { x y z }
      key { id name normalizedName }
    }
    switches {
      id
      name
      switchType
      position { x y z }
      activatedBy { id name }
      activates {
        operation
        target {
          __typename
          ... on MapSwitch { id name }
          ... on MapExtract { id name faction }
        }
      }
    }
    hazards {
      hazardType
      name
      top
      bottom
      position { x y z }
    }
    lootContainers {
      position { x y z }
      lootContainer { name normalizedName }
    }
  }
}
"""

# Plain-language notes for Interchange's conditional extracts.
EXTRACT_NOTES = {
    "saferoom exfil": (
        "Conditional extract. Needs the power switch on (Power Station), the "
        "flush lever in the Burger Spot restroom on Mall Floor 2, and an "
        "Object #11SR keycard swiped at the Saferoom door. Single use — the "
        "keycard is consumed."
    ),
    "hole in the fence": (
        "No backpack allowed. Drop your backpack before stepping in — you "
        "cannot extract while wearing one."
    ),
    "scav camp (co-op)": (
        "Co-op extract. A PMC and a Scav must be in the extract zone at the "
        "same time for it to work."
    ),
    "power station v-ex": (
        "Vehicle extract. Pay the driver in roubles; the car leaves when its "
        "timer ends and it can only be used once per raid."
    ),
    "railway exfil": "Open extract at the railway terminus, north-west corner of the map.",
    "emercom checkpoint": "Open extract at the Emercom checkpoint, south-east highway corner.",
    "path to river (flare)": (
        "Flare extract. Fire a signal flare while standing in the marked "
        "zone to open the extract, then leave before the timer runs out."
    ),
    "smugglers' tunnel": (
        "Extract in the service tunnel beneath the mall — reach it from "
        "the parking garage level."
    ),
}

FACTION_LABEL = {"pmc": "PMC extract", "scav": "Scav extract", "shared": "Shared extract"}

# Floor overrides for extracts, verified against the map: the y-band
# heuristic alone cannot tell the mall's ground-level corridor (Saferoom,
# y~23) from the parking garage below it, nor the outdoor Scav Camp —
# whose position sits inside the config's rough mall rectangle — from
# the garage. Extracts are the raid-critical markers, so they are exact.
EXTRACT_FLOORS = {
    "railway exfil": "exterior",
    "emercom checkpoint": "exterior",
    "scav camp (co-op)": "exterior",
    "path to river (flare)": "exterior",
    "power station v-ex": "exterior",
    "hole in the fence": "exterior",
    "saferoom exfil": "mall1",
    "smugglers' tunnel": "garage",
}

# The Saferoom's own door lock shares the extract's corridor level.
LOCK_FLOOR_OVERRIDES = {
    "object #11sr keycard": "mall1",
}
LOCK_TYPE_LABEL = {
    "door": "Locked door",
    "container": "Locked container",
    "trunk": "Locked car trunk",
}


def fetch_json(url, payload=None, timeout=45):
    data = None
    headers = {"User-Agent": "tarkov-map-app fetch_data.py"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def rotate(x, z, degrees):
    """tarkov.dev applyRotation(): rotate (lng=x, lat=z) by `degrees`."""
    if not degrees:
        return x, z
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return x * cos_a - z * sin_a, x * sin_a + z * cos_a


class Projector:
    """Game position (x, y, z) -> SVG viewBox coordinates (sx, sy)."""

    def __init__(self, cfg, view_box):
        self.scale_x, self.margin_x, self.scale_z, self.margin_y = cfg["transform"]
        self.rotation = cfg.get("coordinateRotation") or 0
        self.vb_w, self.vb_h = view_box
        corners = [self._project(x, z) for x, z in cfg["bounds"]]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        self.min_px, self.max_px = min(xs), max(xs)
        self.min_py, self.max_py = min(ys), max(ys)

    def _project(self, x, z):
        rx, rz = rotate(x, z, self.rotation)
        return (
            self.scale_x * rx + self.margin_x,
            -self.scale_z * rz + self.margin_y,
        )

    def __call__(self, pos):
        px, py = self._project(pos["x"], pos["z"])
        sx = (px - self.min_px) / (self.max_px - self.min_px) * self.vb_w
        sy = (self.max_py - py) / (self.max_py - self.min_py) * self.vb_h
        return round(sx, 2), round(sy, 2)


def floor_for(pos, mall_bounds, override=None):
    """Assign one of exterior / garage / mall1 / mall2.

    Height bands come from the map config's floor extents (First_Floor
    [25, 34], Second_Floor [34, ...]); below the mall's first floor, points
    inside the mall footprint are the parking garage, everything else is
    exterior ground. `override` wins when a curated floor is known.
    """
    if override:
        return override
    y = pos["y"]
    if y >= 34:
        return "mall2"
    if y >= 25:
        return "mall1"
    if mall_bounds:
        (x0, z0), (x1, z1) = mall_bounds
        if min(x0, x1) <= pos["x"] <= max(x0, x1) and min(z0, z1) <= pos["z"] <= max(z0, z1):
            return "garage"
    return "exterior"


def label_floor(label):
    bottom = label.get("bottom")
    top = label.get("top")
    if bottom is not None and bottom >= 34:
        return "mall2"
    if bottom is not None and bottom >= 25:
        return "mall1"
    if bottom is not None and bottom <= -100 and top is not None and top <= 24:
        return "garage"
    return "exterior"


def in_bounds(pos, bounds, margin=25.0):
    xs = [b[0] for b in bounds]
    zs = [b[1] for b in bounds]
    return (
        min(xs) - margin <= pos["x"] <= max(xs) + margin
        and min(zs) - margin <= pos["z"] <= max(zs) + margin
    )


def build_snapshot(map_data, cfg, view_box, source_note=None, fetched_at=None):
    projector = Projector(cfg, view_box)
    mall_bounds = None
    for layer in cfg.get("layers", []):
        for extent in layer.get("extents", []):
            for bounds in extent.get("bounds", []):
                pts = [b for b in bounds if isinstance(b, list)]
                if len(pts) == 2:
                    mall_bounds = pts
                    break

    def marker(name, category, pos, note="", floor_override=None):
        sx, sy = projector(pos)
        sx = min(max(sx, 4.0), view_box[0] - 4.0)
        sy = min(max(sy, 4.0), view_box[1] - 4.0)
        return {
            "name": name,
            "category": category,
            "floor": floor_for(pos, mall_bounds, floor_override),
            "note": note,
            "sx": sx,
            "sy": sy,
            "gx": pos["x"],
            "gy": pos["y"],
            "gz": pos["z"],
        }

    markers = []
    bounds = cfg["bounds"]

    # Extracts (always included, even if a point sits a hair outside bounds).
    for ex in map_data.get("extracts") or []:
        if not ex.get("position"):
            continue
        name = ex.get("name") or "Extract"
        parts = []
        curated = EXTRACT_NOTES.get(name.strip().lower())
        if curated:
            parts.append(curated)
        faction = FACTION_LABEL.get(ex.get("faction") or "shared")
        if faction:
            parts.append(faction + ".")
        if ex.get("switches"):
            parts.append(
                "Activated by: "
                + ", ".join(sw.get("name") or "switch" for sw in ex["switches"])
                + "."
            )
        if ex.get("transferItem"):
            item = ex["transferItem"].get("item") or {}
            count = ex["transferItem"].get("count") or 1
            suffix = f" x{int(count)}" if count and count > 1 else ""
            parts.append(f"Requires: {item.get('name', 'item')}{suffix}.")
        markers.append(
            marker(
                name,
                "extract",
                ex["position"],
                " ".join(parts),
                EXTRACT_FLOORS.get(name.strip().lower()),
            )
        )

    # Transits.
    for tr in map_data.get("transits") or []:
        if not tr.get("position"):
            continue
        dest = (tr.get("map") or {}).get("name")
        name = tr.get("description") or (f"Transit to {dest}" if dest else "Transit")
        note = tr.get("conditions") or (f"Transit to {dest}." if dest else "Transit.")
        markers.append(marker(name, "transit", tr["position"], note))

    # Spawns + boss areas (boss positions join boss data by zoneName,
    # exactly like the tarkov.dev map page does).
    bosses = map_data.get("bosses") or []
    for spawn in map_data.get("spawns") or []:
        pos = spawn.get("position")
        if not pos or not in_bounds(pos, bounds):
            continue
        categories = spawn.get("categories") or []
        sides = spawn.get("sides") or []
        zone = spawn.get("zoneName")
        if "boss" in categories:
            matched = [b for b in bosses if zone in boss_spawn_keys(b)]
            if not matched:
                if "bot" in categories and "scav" in sides:
                    markers.append(
                        marker(f"Scav spawn{zone_suffix(zone)}", "scav_spawn", pos, "Scav spawn point.")
                    )
                continue
            names = []
            for boss in matched:
                boss_name = boss_display_name(boss)
                chance = boss.get("spawnChance")
                if chance is not None:
                    pct = chance * 100 if chance <= 1 else chance
                    names.append(f"{boss_name} ({pct:.0f}% spawn chance)")
                else:
                    names.append(boss_name)
            title = (
                f"{boss_display_name(matched[0])} spawn area"
                if len(matched) == 1
                else "Boss spawn area"
            )
            markers.append(
                marker(title, "boss", pos, "Boss can spawn here: " + "; ".join(names) + ".")
            )
        elif "player" in categories and ("pmc" in sides or "all" in sides):
            markers.append(
                marker(f"PMC spawn{zone_suffix(zone)}", "pmc_spawn", pos, "Possible PMC spawn point.")
            )
        elif "sniper" in categories:
            markers.append(
                marker(f"Sniper Scav spawn{zone_suffix(zone)}", "scav_spawn", pos, "Sniper Scav spawn point.")
            )
        elif "scav" in sides and ("bot" in categories or "all" in categories):
            markers.append(
                marker(f"Scav spawn{zone_suffix(zone)}", "scav_spawn", pos, "Scav spawn point.")
            )

    # Locked doors / containers (the API key field is the item that opens it).
    for lock in map_data.get("locks") or []:
        pos = lock.get("position")
        if not pos or not in_bounds(pos, bounds):
            continue
        key = lock.get("key") or {}
        # Live API: key is an Item object. Snapshot exports: key is the
        # item's name as a plain string. Handle both.
        key_name = key if isinstance(key, str) else key.get("name")
        kind = LOCK_TYPE_LABEL.get(lock.get("lockType") or "", "Lock")
        name = key_name or kind
        note = kind + (f" — opens with: {key_name}." if key_name else ".")
        if lock.get("needsPower"):
            note += " Needs the power on."
        override = LOCK_FLOOR_OVERRIDES.get((key_name or "").strip().lower())
        markers.append(marker(name, "lock", pos, note, override))

    # Switches.
    for sw in map_data.get("switches") or []:
        pos = sw.get("position")
        if not pos or not in_bounds(pos, bounds):
            continue
        parts = []
        if sw.get("activatedBy"):
            parts.append(f"Activated by: {sw['activatedBy'].get('name')}.")
        targets = []
        for op in sw.get("activates") or []:
            target = op.get("target") or {}
            if target.get("name"):
                targets.append(target["name"])
        if targets:
            parts.append("Activates: " + ", ".join(targets) + ".")
        markers.append(
            marker(sw.get("name") or "Switch", "switch", pos, " ".join(parts))
        )

    # Hazards.
    for hz in map_data.get("hazards") or []:
        pos = hz.get("position")
        if not pos:
            continue
        htype = hz.get("hazardType")
        note = f"Hazard area{f' ({htype})' if htype else ''}. Watch your step."
        markers.append(marker(hz.get("name") or "Hazard", "hazard", pos, note))

    # Loot containers.
    for entry in map_data.get("lootContainers") or []:
        pos = entry.get("position")
        container = entry.get("lootContainer") or {}
        if not pos or not in_bounds(pos, bounds):
            continue
        norm = container.get("normalizedName") or ""
        note = ""
        if norm in ("container_ground-cache", "container_buried-barrel-cache") or norm in (
            "ground-cache",
            "buried-barrel-cache",
        ):
            note = "Hidden stash — it may not spawn in every raid."
        markers.append(
            marker(container.get("name") or "Loot container", "loot", pos, note)
        )

    labels = []
    for label in cfg.get("labels", []):
        pos = label.get("position") or []
        if len(pos) < 2:
            continue
        sx, sy = projector({"x": pos[0], "z": pos[1]})
        labels.append(
            {"name": label.get("text", ""), "floor": label_floor(label), "sx": sx, "sy": sy}
        )

    return {
        "map": map_data.get("name") or "Interchange",
        "normalizedName": map_data.get("normalizedName") or "interchange",
        "source": source_note
        or (
            "Markers: tarkov.dev GraphQL API (api.tarkov.dev/graphql). "
            "Transform, bounds, floor extents and labels: the-hideout/tarkov-dev "
            "src/data/maps.json. Basemap: the-hideout/tarkov-dev-svg-maps "
            "Interchange.svg. Community data, CC BY-NC-SA 4.0."
        ),
        "fetchedAt": fetched_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transform": {
            "scale": cfg["transform"][0],
            "marginX": cfg["transform"][1],
            "marginY": cfg["transform"][3],
            "rotation": cfg.get("coordinateRotation"),
            "bounds": cfg["bounds"],
            "viewBox": list(view_box),
        },
        "labels": labels,
        "markers": markers,
    }


def zone_suffix(zone):
    return f" — {zone}" if zone else ""


def boss_display_name(boss):
    return (boss.get("boss") or {}).get("name") or boss.get("name") or "Boss"


def boss_spawn_keys(boss):
    """Zone names a boss can spawn at, in either data shape."""
    keys = [sl.get("spawnKey") for sl in boss.get("spawnLocations") or []]
    keys += list(boss.get("spawnKeys") or [])
    return [k for k in keys if k]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=float, default=10.0)
    parser.add_argument(
        "--from-snapshot",
        metavar="FILE",
        help=(
            "Load marker data from a saved tarkov.dev API-format maps "
            "export (a JSON list of maps, or {data: {maps: [...]}}) "
            "instead of querying the live API — e.g. while the API is down."
        ),
    )
    args = parser.parse_args()

    svg_text = SVG_PATH.read_text()
    match = re.search(r'viewBox="([\d.\s]+)"', svg_text)
    view_box = tuple(float(v) for v in match.group(1).split()[2:4]) if match else (1127.6852, 947.02582)

    print(f"Fetching map config from {MAPS_JSON_URL}")
    maps_config = fetch_json(MAPS_JSON_URL)
    interchange = next(m for m in maps_config if m.get("normalizedName") == "interchange")
    cfg = next(m for m in interchange["maps"] if m.get("projection") == "interactive")

    map_data = None
    source_note = None
    fetched_at = None
    if args.from_snapshot:
        raw = json.loads(Path(args.from_snapshot).read_text())
        maps_list = raw
        if isinstance(raw, dict):
            maps_list = raw.get("data", {}).get("maps", [])
        map_data = next(
            m for m in maps_list if m.get("normalizedName") == "interchange"
        )
        meta_path = Path(args.from_snapshot).parent / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if meta.get("fetchedAt"):
                fetched_at = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(meta["fetchedAt"] / 1000)
                )
        source_note = (
            "Markers: snapshot of the tarkov.dev maps data (API format), "
            f"fetched {fetched_at or 'on an unknown date'}, via a public "
            "mirror — refresh with scripts/fetch_data.py against the live "
            "API when it is reachable. Transform, bounds, floor extents "
            "and labels: the-hideout/tarkov-dev src/data/maps.json. "
            "Basemap: the-hideout/tarkov-dev-svg-maps Interchange.svg. "
            "Community data, CC BY-NC-SA 4.0."
        )
        print(f"Loaded marker data from snapshot {args.from_snapshot}")

    last_error = None
    for attempt in range(1, args.attempts + 1) if map_data is None else []:
        try:
            print(f"Querying tarkov.dev API (attempt {attempt}/{args.attempts})")
            result = fetch_json(API_URL, {"query": QUERY})
            if result.get("errors"):
                raise RuntimeError(str(result["errors"]))
            map_data = result["data"]["maps"][0]
            break
        except Exception as exc:  # noqa: BLE001 - report and retry any failure
            last_error = exc
            print(f"  failed: {exc}")
            if attempt < args.attempts:
                time.sleep(args.delay)
    if map_data is None:
        print(f"API unavailable after {args.attempts} attempts: {last_error}", file=sys.stderr)
        print("Existing snapshot left untouched.", file=sys.stderr)
        return 1

    snapshot = build_snapshot(map_data, cfg, view_box, source_note, fetched_at)
    OUT_PATH.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n")

    counts = {}
    for m in snapshot["markers"]:
        counts[m["category"]] = counts.get(m["category"], 0) + 1
    print(f"Wrote {OUT_PATH}: {len(snapshot['markers'])} markers, {len(snapshot['labels'])} labels")
    for category in sorted(counts):
        print(f"  {category}: {counts[category]}")
    floors = {}
    for m in snapshot["markers"]:
        floors[m["floor"]] = floors.get(m["floor"], 0) + 1
    print("  floors:", floors)
    for m in snapshot["markers"]:
        if m["category"] == "extract":
            print(f"  extract {m['name']!r}: floor={m['floor']} svg=({m['sx']}, {m['sy']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
