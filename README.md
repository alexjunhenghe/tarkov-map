# tarkov-map — Interchange map prototype (Proa)

An interactive Escape from Tarkov **Interchange** map built with
[Proa](https://proa.so) (Rust). One server-rendered page at `/` inlines the
tarkov.dev community SVG basemap and layers 1,101 markers over it — extracts,
PMC/Scav spawns, boss areas, locked doors, switches, hazards, transits and
loot containers — with true floor switching, pan/zoom, layer toggles and a
click-for-details card.

This is a **planning/reference tool** for use outside of raids. It is not an
overlay and does not interact with the game in any way.

Unofficial fan tool — not affiliated with Battlestate Games.

## Live demo

**https://alexjunhenghe.github.io/tarkov-map/** — a static deployment of
this Proa build, published from the `gh-pages` branch. The app is
snapshot-driven (marker data is embedded at build time and interactivity
is client-side), so the static deployment behaves like the server-rendered
page. To redeploy after a data or code change, re-render the page from a
running server and republish the captured HTML/JSON/static assets to
`gh-pages` with asset paths made relative.

## Deploy the server (Railway)

Proa's recommended target. The repo is prepped: `Dockerfile` and
`railway.json` are adapted from Proa's Railway guide, and the app already
reads `PORT`/`PROA_HOST` and answers `/healthz` and `/readyz`.

1. Create a Railway project and connect this GitHub repo (Railway builds
   the Dockerfile on every push to `main`).
2. In the service, open Settings → Networking → Generate Domain.
3. Optional: after the first deploy, add the guide's BuildKit cache
   mounts (keyed with your Railway service id) to the Dockerfile to speed
   up rebuilds.

## Run it

Prerequisites: a Rust toolchain and the Proa CLI.

```console
cargo install proa-cli --locked
proa dev            # http://localhost:3000
```

Production build:

```console
proa build
```

The HTML page lives at `/`; Proa also serves a semantic Markdown twin of the
page at `/index.md`, and the marker snapshot itself at
`/data/interchange.json`.

No database setup is needed to view the map — the page is rendered from the
committed snapshot in `data/interchange.json`.

## What works

- **Floors** — Exterior, Parking Garage, Mall Floor 1, Mall Floor 2 tabs.
  Switching hides the inactive SVG floor groups and refits the camera to the
  active floor's own bounds (interior floors are fitted to the mall footprint,
  not the whole canvas).
- **Camera** — drag to pan, mouse wheel to zoom at the cursor, two-finger
  pinch on touch screens, FIT button to reset the current floor's view.
- **Markers** — 1,101 markers positioned with tarkov.dev's published
  coordinate transform (see below). Category toggles in the sidebar with
  beginner-clean defaults: extracts, PMC spawns, Scav spawns and boss areas
  on; locks, switches, hazards, transits and loot off. The 823 loot
  containers are clustered into count badges while zoomed out and resolve
  into individual markers as you zoom in.
- **Details** — clicking a marker (or an entry in the server-rendered
  Extracts list) shows its name, category, floor and a plain-language note.
  Conditional extracts are explained: Saferoom Exfil needs the power on, the
  flush lever in the Burger Spot restroom on Mall Floor 2, and an Object
  #11SR keycard (single use); Hole in the Fence takes no backpack; Scav Camp
  is a PMC + Scav co-op extract; Power Station V-Ex is a paid vehicle
  extract.
- **Labels** — the 77 area/store labels from the tarkov.dev map config are
  drawn per floor (IDEA, Goshan, OLI, Kiba, Power Station, garage sections…).

## Data

Everything is committed as a snapshot, so the app works offline:

- `assets/Interchange.svg` — basemap from
  [the-hideout/tarkov-dev-svg-maps](https://github.com/the-hideout/tarkov-dev-svg-maps),
  inlined into the page so its cartography styles come with it.
- `data/interchange.json` — the marker snapshot the page renders from.
  Per-marker it carries the category, floor, note, game coordinates and
  precomputed SVG coordinates (`sx`/`sy`), plus the transform metadata and
  the fetch timestamp.
- `scripts/fetch_data.py` — the refresh path (Python 3, stdlib only).

### Coordinate transform

Taken verbatim from the open-source tarkov.dev site
(`the-hideout/tarkov-dev`, `src/data/maps.json` + its map page code):
Interchange uses transform `[0.265, 150.6, 0.265, 134.6]`, a 180°
coordinate rotation, and bounds `[[598, -442], [-433, 426]]`. Game
coordinates are rotated 180°, projected with that transformation into
Leaflet CRS pixels, then normalized over the bounds rectangle into the SVG
viewBox (`0 0 1127.6852 947.02582`). Floors are assigned from each marker's
height against the config's floor extents (Mall Floor 1 from y 25, Mall
Floor 2 from y 34) plus the mall footprint for the garage level, with
hand-verified overrides for the nine extracts. One border case: the Path to
River flare extract sits a few units past the published bounds edge, so its
marker is clamped to the canvas edge.

Sanity checks from the current snapshot: Railway Exfil lands at the rail
terminus corner, Emercom Checkpoint at the opposite highway corner, the
Power Station vehicle extract next to the Power Station label artwork, and
Saferoom Exfil inside the mall on Mall Floor 1.

### Refresh the snapshot

```console
python3 scripts/fetch_data.py
```

This re-reads the map config from the-hideout/tarkov-dev, queries the
tarkov.dev GraphQL API (`https://api.tarkov.dev/graphql`) for Interchange,
rebuilds `data/interchange.json`, and prints per-category counts. The app
embeds the snapshot at compile time, so rebuild afterwards (`proa build`).

The committed snapshot was fetched on **2026-09-23** from a public mirror of
the tarkov.dev API-format map data, because api.tarkov.dev was returning
"GraphQL server unavailable" throughout the build session (2026-10-15);
`scripts/fetch_data.py --from-snapshot <file>` rebuilds from a saved
API-format export the same way. Marker counts in this snapshot: 9 extracts,
2 transits, 130 PMC spawns, 71 Scav spawns, 7 boss spawn areas (Killa,
Tagilla), 28 locks (15 keyed doors), 6 switches, 25 hazards, 823 loot
containers. Switch notes are name-only in this snapshot — the export lacks
activation links; a live-API refresh restores them.

Two upstream data errors are corrected in `scripts/fetch_data.py` (and
survive refreshes): the API's Scav Camp (Co-Op) extract position sits
inside the mall, so it is overridden to the map config's "Scav Camp"
label position on the west highway, where the extract actually is; and
boss areas are only taken from spawn points inside the mall footprint —
the API also tags west-highway ZoneGoshan points as Killa spawns, and
those points render as the Scav spawns they are instead.

## Scope and limitations

- **Parking Garage basemap**: the upstream SVG has no standalone garage
  floor plate — the garage artwork lives inside the `Ground_Level` group.
  The Parking Garage tab therefore shows the Ground_Level artwork fitted to
  the mall footprint (where the garage is), with garage-level markers. Mall
  Floor 1 shows `First_Floor`, Mall Floor 2 shows `Second_Floor`, Exterior
  shows the full `Ground_Level`.
- Floor assignment is height/footprint-based (plus curated extract
  overrides); a handful of basement-corridor points may sit on a neighboring
  tab. Extract floors are hand-verified.
- Interactivity (pan/zoom, floor switching, toggles, detail card) is a small
  vanilla JS asset (`public/map.js`) rather than an RSJS island: Proa
  server-renders the shell, floor tabs, layer panel and extract list, and
  the script hydrates the map from `/data/interchange.json`. JavaScript is
  required for the interactive map; the extract list and page content are in
  the server-rendered HTML.
- Single map (Interchange) and a static snapshot — no live raid state, no
  other maps yet.

## License and attribution

Basemap and marker data are community data from
[The Hideout / tarkov.dev](https://tarkov.dev), licensed
**CC BY-NC-SA 4.0** — attribution required, non-commercial, share-alike.
This project is a planning/reference tool; the license prohibits cheat
software and nothing here is designed for in-raid use. Escape from Tarkov
is a trademark of Battlestate Games; this is an unofficial fan project.
