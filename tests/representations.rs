use std::sync::Arc;

use axum::{
    body::Body,
    http::{header, Request, StatusCode},
    response::Response,
};
use http_body_util::BodyExt;
use tower::ServiceExt;

#[path = "../src/app.rs"]
mod app;
#[path = "../src/components/mod.rs"]
mod components;
#[path = "../src/db.rs"]
mod db;
#[path = "../src/endpoints/mod.rs"]
mod endpoints;
#[path = "../src/error.rs"]
mod error;
#[path = "../src/layouts/mod.rs"]
mod layouts;
#[path = "../src/loader.rs"]
mod loader;
#[path = "../src/pages/mod.rs"]
mod pages;
#[path = "../src/routes.rs"]
mod routes;
#[path = "../src/static_assets.rs"]
mod static_assets;

async fn body(response: Response) -> Vec<u8> {
    response
        .into_body()
        .collect()
        .await
        .unwrap()
        .to_bytes()
        .to_vec()
}

#[tokio::test(flavor = "multi_thread")]
async fn canonical_and_explicit_markdown_share_one_page_policy() {
    let database_url = std::env::var("DATABASE_URL").expect("proa test supplies DATABASE_URL");
    let pool = db::connect(&database_url).await.unwrap();
    let loader = Arc::new(loader::AppLoader::new(pool.clone()));
    let app = routes::router(app::AppState {
        db: pool.clone(),
        loader,
    });

    let html = app
        .clone()
        .oneshot(Request::builder().uri("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(html.status(), StatusCode::OK);
    assert!(html.headers()[header::CONTENT_TYPE]
        .to_str()
        .unwrap()
        .starts_with("text/html"));
    assert_eq!(html.headers()[header::VARY], "Accept");
    assert!(html.headers()[header::LINK]
        .to_str()
        .unwrap()
        .contains("/index.md"));

    let refused_markdown = app
        .clone()
        .oneshot(
            Request::builder()
                .uri("/")
                .header(header::ACCEPT, "text/markdown;q=0, text/html")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(refused_markdown.headers()[header::CONTENT_TYPE]
        .to_str()
        .unwrap()
        .starts_with("text/html"));

    let negotiated = app
        .clone()
        .oneshot(
            Request::builder()
                .uri("/")
                .header(header::ACCEPT, "text/markdown")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(negotiated.headers()[header::CONTENT_TYPE]
        .to_str()
        .unwrap()
        .starts_with("text/markdown"));
    let negotiated = body(negotiated).await;

    let explicit = app
        .oneshot(
            Request::builder()
                .uri("/index.md")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(explicit.headers()[header::CONTENT_TYPE]
        .to_str()
        .unwrap()
        .starts_with("text/markdown"));
    let explicit = body(explicit).await;
    assert_eq!(negotiated, explicit);
    let markdown = String::from_utf8(explicit).unwrap();
    assert!(!markdown.contains("<html"));
    assert!(!markdown.contains("/static/"));

    pool.close().await;
}
