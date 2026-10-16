use proa_core::{
    DataLoader, MdRenderSync, StaticRaw, WebContext, WebRenderSync, WriteBuf, WriteError,
};
use proa_macros::{html_sync, md_sync};

/// Access to the Interchange marker snapshot.
///
/// The snapshot lives at `data/interchange.json` (repo root) and is produced
/// by `scripts/fetch_data.py` from the tarkov.dev GraphQL API plus the map
/// config published in the-hideout/tarkov-dev. It is embedded into the
/// binary at compile time so the running app has no filesystem dependency,
/// and the same bytes are served verbatim at `/data/interchange.json` for
/// the client-side map script.
///
/// This lives inside the page module because Proa's site check requires
/// every file under `src/pages/` to expose a handler or render function.
mod map_data {
    use std::sync::OnceLock;

    use serde::Deserialize;

    pub const SNAPSHOT_JSON: &str = include_str!("../../data/interchange.json");

    #[derive(Debug, Deserialize)]
    #[allow(dead_code)] // every field is consumed by the client script's JSON
    pub struct Snapshot {
        #[serde(default)]
        pub markers: Vec<Marker>,
        #[serde(default)]
        pub labels: Vec<MapLabel>,
    }

    #[derive(Debug, Clone, Deserialize)]
    #[allow(dead_code)]
    pub struct Marker {
        pub name: String,
        pub category: String,
        pub floor: String,
        /// Plain-language note (extract conditions, key names, boss names).
        #[serde(default)]
        pub note: String,
        /// Position in the basemap SVG's own coordinate space (viewBox
        /// units), precomputed by scripts/fetch_data.py with the
        /// tarkov.dev transform.
        pub sx: f64,
        pub sy: f64,
    }

    #[derive(Debug, Clone, Deserialize)]
    #[allow(dead_code)]
    pub struct MapLabel {
        pub name: String,
        pub floor: String,
        pub sx: f64,
        pub sy: f64,
    }

    pub fn snapshot() -> &'static Snapshot {
        static SNAPSHOT: OnceLock<Snapshot> = OnceLock::new();
        SNAPSHOT.get_or_init(|| {
            serde_json::from_str(SNAPSHOT_JSON)
                .expect("data/interchange.json must be valid snapshot JSON")
        })
    }

    pub fn extracts() -> Vec<&'static Marker> {
        snapshot()
            .markers
            .iter()
            .filter(|marker| marker.category == "extract")
            .collect()
    }
}

/// Floor ids in display order: (id used in data + DOM, display name).
const FLOORS: [(&str, &str); 4] = [
    ("exterior", "Exterior"),
    ("garage", "Parking Garage"),
    ("mall1", "Mall Floor 1"),
    ("mall2", "Mall Floor 2"),
];

/// Marker categories in display order: (id used in data + DOM, display
/// name, on by default). Defaults are beginner-clean: extracts, spawns
/// and boss areas on; the dense loot layer starts off.
const CATEGORIES: [(&str, &str, bool); 9] = [
    ("extract", "Extracts", true),
    ("pmc_spawn", "PMC spawns", true),
    ("scav_spawn", "Scav spawns", true),
    ("boss", "Boss areas", true),
    ("lock", "Locked doors", false),
    ("switch", "Switches", false),
    ("hazard", "Hazards", false),
    ("transit", "Transits", false),
    ("loot", "Loot containers", false),
];

/// The Interchange basemap (the-hideout/tarkov-dev-svg-maps, CC BY-NC-SA
/// 4.0), inlined so the client script can toggle its floor layer groups
/// (Ground_Level, First_Floor, Second_Floor) directly in the DOM.
const BASEMAP_SVG: &str = include_str!("../../assets/Interchange.svg");

#[derive(Debug, Clone)]
pub struct HomePage {
    floors: &'static [(&'static str, &'static str)],
    categories: &'static [(&'static str, &'static str, bool)],
    extracts: Vec<&'static map_data::Marker>,
}

impl HomePage {
    pub fn new() -> Self {
        Self {
            floors: &FLOORS,
            categories: &CATEGORIES,
            extracts: map_data::extracts(),
        }
    }
}


#[derive(Debug, Clone, Copy)]
struct FloorTab {
    id: &'static str,
    name: &'static str,
}

impl<L: DataLoader> WebRenderSync<L> for FloorTab {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <button type="button" class="floor-tab" data-floor-tab={self.id}>{self.name}</button>
        }
        .render(cx)
    }
}

impl<L: DataLoader, B: WriteBuf> MdRenderSync<L, B> for FloorTab {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        MdRenderSync::render_md(self.name, cx)
    }
}

#[derive(Debug, Clone, Copy)]
struct LayerToggle {
    id: &'static str,
    name: &'static str,
    default_on: bool,
}

impl<L: DataLoader> WebRenderSync<L> for LayerToggle {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <label class="layer-toggle" data-layer-toggle>
                <input
                    type="checkbox"
                    data-layer={self.id}
                    data-default-on={if self.default_on { "true" } else { "false" }}
                />
                <span class="layer-name">{self.name}</span>
                <span class="layer-count" data-count-for={self.id}></span>
            </label>
        }
        .render(cx)
    }
}

impl<L: DataLoader, B: WriteBuf> MdRenderSync<L, B> for LayerToggle {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        MdRenderSync::render_md(self.name, cx)
    }
}

#[derive(Debug, Clone, Copy)]
struct ExtractItem<'a> {
    name: &'a str,
    note: &'a str,
}

impl<L: DataLoader> WebRenderSync<L> for ExtractItem<'_> {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <li data-extract-item>
                <button type="button" class="extract-link" data-extract-name={self.name}>
                    {self.name}
                </button>
                <p class="extract-note">{self.note}</p>
            </li>
        }
        .render(cx)
    }
}

impl<'a, L: DataLoader, B: WriteBuf> MdRenderSync<L, B> for ExtractItem<'a> {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        md_sync! { { self.name } "\n\n" { self.note } }.render_md(cx)
    }
}

impl<L: DataLoader> WebRenderSync<L> for HomePage {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <main data-map-page>
                <header class="topbar">
                    <a class="wordmark" href="/">"TARKOV MAP"</a>
                    <span>"PROA PROTOTYPE · INTERCHANGE"</span>
                </header>
                <section class="map-intro">
                    <p class="kicker">"ESCAPE FROM TARKOV · INTERACTIVE MAP"</p>
                    <h1 class="map-title">"Interchange"</h1>
                    <p class="lede">
                        "Raid-first map of the ULTRA mall and its surroundings: extracts, spawns, loot containers and locked doors across the exterior, the parking garage and both mall floors. Server-rendered by Proa; one small script adds pan, zoom, floor switching and marker details."
                    </p>
                </section>
                <section data-map-app class="map-app">
                    <div class="map-toolbar">
                        <div class="floor-tabs" data-floor-tabs>
                            <span class="toolbar-label">"Floor"</span>
                            {for floor in self.floors.iter() {
                                html_sync! {
                                    {FloorTab { id: floor.0, name: floor.1 }}
                                }
                            }}
                        </div>
                        <button type="button" class="fit-button" data-fit-button>"FIT"</button>
                    </div>
                    <div class="map-layout">
                        <div data-map-stage class="map-stage" id="map-stage">
                            {proa_macros::content_part!("basemap", StaticRaw(BASEMAP_SVG))}
                        </div>
                        <aside data-map-side class="map-side">
                            <section data-layer-panel class="side-panel">
                                <h2>"Layers"</h2>
                                <div class="layer-list">
                                    {for category in self.categories.iter() {
                                        html_sync! {
                                            {LayerToggle { id: category.0, name: category.1, default_on: category.2 }}
                                        }
                                    }}
                                </div>
                            </section>
                            <section data-detail-card class="side-panel" id="detail-card">
                                <h2>"Marker details"</h2>
                                <p class="detail-name" id="detail-name">"Nothing selected"</p>
                                <p class="detail-meta" id="detail-meta"></p>
                                <p class="detail-note" id="detail-note">
                                    "Select a marker on the map to see what it is and how it works."
                                </p>
                            </section>
                            <section data-extract-list class="side-panel">
                                <h2>"Extracts"</h2>
                                <ul class="extract-list">
                                    {for extract in self.extracts.iter() {
                                        html_sync! {
                                            {ExtractItem { name: extract.name.as_str(), note: extract.note.as_str() }}
                                        }
                                    }}
                                </ul>
                            </section>
                        </aside>
                    </div>
                    <p class="map-note">
                        "The basemap is the tarkov.dev community SVG; markers come from the bundled snapshot served at /data/interchange.json."
                    </p>
                </section>
                <footer class="receipt">
                    <span>
                        "Basemap © The Hideout / tarkov.dev contributors — CC BY-NC-SA 4.0"
                    </span>
                    <span>"Marker data: tarkov.dev community data"</span>
                    <strong>"Unofficial fan tool — not affiliated with Battlestate Games"</strong>
                </footer>
                <script src="/static/map.js"></script>
            </main>
        }
        .render(cx)
    }
}

impl<L: DataLoader, B: WriteBuf> MdRenderSync<L, B> for HomePage {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        proa_macros::omit!("/static/map.js");
        proa_macros::omit!("basemap", "Basemap SVG artwork renders only in the browser view");
        md_sync! { r###"
            /

            TARKOV MAP

            PROA PROTOTYPE · INTERCHANGE

            ESCAPE FROM TARKOV · INTERACTIVE MAP

            Interchange

            Raid-first map of the ULTRA mall and its surroundings: extracts, spawns, loot containers and locked doors across the exterior, the parking garage and both mall floors\. Server-rendered by Proa; one small script adds pan, zoom, floor switching and marker details\.

            Floor

            {for floor in self.floors.iter() {
            {FloorTab { id: floor.0, name: floor.1 }}
            }}

            FIT

            Layers

            {for category in self.categories.iter() {
            {LayerToggle { id: category.0, name: category.1, default_on: category.2 }}
            }}

            Marker details

            Nothing selected

            Select a marker on the map to see what it is and how it works\.

            Extracts

            {for extract in self.extracts.iter() {
            {ExtractItem { name: extract.name.as_str(), note: extract.note.as_str() }}
            }}

            The basemap is the tarkov\.dev community SVG; markers come from the bundled snapshot served at /data/interchange\.json\.

            Basemap © The Hideout / tarkov\.dev contributors — CC BY-NC-SA 4\.0

            Marker data: tarkov\.dev community data

            Unofficial fan tool — not affiliated with Battlestate Games
            "###
        }
        .render_md(cx)
    }
}

use axum::{extract::State, http::HeaderMap, response::IntoResponse};
use proa_framework_axum::{
    explicit_markdown_async_with_loader, negotiate_async_with_loader, MarkdownAlternate,
    RouteResponse,
};
use proa_stream::DataResolver;

use crate::{app::AppState, error::AppError, layouts::RootDocument};

pub async fn handler(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, AppError> {
    let resolver = DataResolver::request_scope(state.loader.clone());
    let html = RouteResponse::ssr_async_with_loader(
        RootDocument {
            title: "Interchange — Tarkov Map",
            content: proa_core::to_async(HomePage::new()),
        },
        resolver.clone(),
    );
    Ok(negotiate_async_with_loader(
        &headers,
        html,
        proa_core::to_md_async(HomePage::new()),
        resolver,
        MarkdownAlternate::new("/index.md"),
    ))
}

pub async fn markdown(State(state): State<AppState>) -> Result<impl IntoResponse, AppError> {
    let resolver = DataResolver::request_scope(state.loader.clone());
    Ok(explicit_markdown_async_with_loader(
        proa_core::to_md_async(HomePage::new()),
        resolver,
    ))
}

/// Serves the bundled marker snapshot verbatim for the client map script.
pub async fn data_json() -> impl IntoResponse {
    (
        [(axum::http::header::CONTENT_TYPE, "application/json")],
        map_data::SNAPSHOT_JSON,
    )
}
