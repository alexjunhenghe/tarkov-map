use proa_core::{DataLoader, MdRenderSync, WebContext, WebRenderSync, WriteBuf, WriteError};
use proa_macros::{html_sync, md_sync};

/// Access to the item price index.
///
/// The index lives at `data/prices.json` (repo root) and is produced by
/// `scripts/fetch_prices.py` — from the tarkov.dev GraphQL API when it is
/// reachable, otherwise from the SPT open game database as a clearly
/// labelled seed snapshot. It is embedded into the binary at compile
/// time and served verbatim at `/data/prices.json`; the page's client
/// script fetches it once and does search + detail entirely in the
/// browser, so lookups never wait on a live API.
mod price_data {
    pub const PRICES_JSON: &str = include_str!("../../data/prices.json");
}

/// Item price lookup page. All data work happens client-side in
/// /static/items.js against the bundled price index; this component
/// renders the static shell (search box, results mount point, detail
/// panel) that the script fills in.
#[derive(Debug, Clone, Copy)]
pub struct ItemsPage;

impl<L: DataLoader> WebRenderSync<L> for ItemsPage {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        html_sync! {
            <main data-items-page>
                <header class="topbar">
                    <a class="wordmark" href="/">"TARKOV MAP"</a>
                    <nav class="topbar-nav">
                        <a class="topbar-link" href="/">"Interchange map"</a>
                        <span>"PRICE LOOKUP"</span>
                    </nav>
                </header>
                <section class="map-intro">
                    <p class="kicker">"ESCAPE FROM TARKOV · ITEM PRICES"</p>
                    <h1 class="map-title">"Item prices"</h1>
                    <p class="lede">
                        "Flea market values and trader prices for every item, in one fast lookup. The whole price index is a bundled snapshot served with the page — searching it never waits on a network call."
                    </p>
                </section>
                <section data-price-app class="price-app">
                    <div class="price-search">
                        <span class="toolbar-label">"Search items"</span>
                        <input
                            id="price-search-input"
                            class="price-search-input"
                            type="search"
                            placeholder="e.g. LEDX, Salewa, M4A1…"
                            aria-label="Search items"
                            autocomplete="off"
                        />
                        <p class="price-status" id="price-status">"Loading the price index…"</p>
                        <p class="seed-note" id="seed-note"></p>
                    </div>
                    <div class="price-layout">
                        <div data-price-results class="price-results" id="price-results"></div>
                        <section
                            data-price-detail
                            class="side-panel price-detail"
                            id="price-detail"
                            aria-live="polite"
                        >
                            <h2>"Item details"</h2>
                            <div id="price-detail-body">
                                <p class="detail-name" id="price-name">"Nothing selected"</p>
                                <p class="detail-note" id="price-note">
                                    "Search for an item and select it to see its flea value, the best trader to sell to, and its price per slot."
                                </p>
                            </div>
                        </section>
                    </div>
                </section>
                <footer class="receipt">
                    <span>"Price index: bundled snapshot served at /data/prices.json"</span>
                    <span>
                        "Price data: tarkov.dev community data; seed snapshot: SPT open database"
                    </span>
                    <strong>"Unofficial fan tool — not affiliated with Battlestate Games"</strong>
                </footer>
                <script src="/static/items.js"></script>
            </main>
        }
        .render(cx)
    }
}

impl<L: DataLoader, B: WriteBuf> MdRenderSync<L, B> for ItemsPage {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        proa_macros::omit!("/static/items.js");
        proa_macros::omit!("e.g. LEDX, Salewa, M4A1…");
        md_sync! { r###"
            /items

            TARKOV MAP

            Interchange map

            PRICE LOOKUP

            ESCAPE FROM TARKOV · ITEM PRICES

            Item prices

            Flea market values and trader prices for every item, in one fast lookup\. The whole price index is a bundled snapshot served with the page — searching it never waits on a network call\.

            Search items

            Loading the price index…

            Item details

            Nothing selected

            Search for an item and select it to see its flea value, the best trader to sell to, and its price per slot\.

            Price index: bundled snapshot served at /data/prices\.json

            Price data: tarkov\.dev community data; seed snapshot: SPT open database

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
            title: "Item prices — Tarkov Map",
            content: proa_core::to_async(ItemsPage),
        },
        resolver.clone(),
    );
    Ok(negotiate_async_with_loader(
        &headers,
        html,
        proa_core::to_md_async(ItemsPage),
        resolver,
        MarkdownAlternate::new("/items.md"),
    ))
}

pub async fn markdown(State(state): State<AppState>) -> Result<impl IntoResponse, AppError> {
    let resolver = DataResolver::request_scope(state.loader.clone());
    Ok(explicit_markdown_async_with_loader(
        proa_core::to_md_async(ItemsPage),
        resolver,
    ))
}

/// Serves the bundled price index verbatim for the client lookup script.
pub async fn prices_json() -> impl IntoResponse {
    (
        [(axum::http::header::CONTENT_TYPE, "application/json")],
        price_data::PRICES_JSON,
    )
}
