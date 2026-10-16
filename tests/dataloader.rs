#![allow(dead_code)]

// The scaffold's version of this test rendered the starter home page, which
// embedded DatabaseBadge + DatabaseCard. The map page no longer embeds the
// database widgets, so the test now renders the two real components
// directly against one request scope — the behavior under test is the
// same: two components sharing one keyed load deduplicate to a single
// origin call per request.

use std::{
    future::Future,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
};

use proa_core::{DataLoader, LoadError, LoadRequest, LoadValue, MdRender, WebContext, WebRender};
use proa_stream::DataResolver;

#[path = "../src/app.rs"]
mod app;
#[path = "../src/components/mod.rs"]
mod components;
#[path = "../src/error.rs"]
mod error;
#[path = "../src/layouts/mod.rs"]
mod layouts;
#[path = "../src/loader.rs"]
mod loader;
#[path = "../src/pages/mod.rs"]
mod pages;

struct InstrumentedLoader {
    origin_loads: Arc<AtomicUsize>,
}

impl DataLoader for InstrumentedLoader {
    fn load(
        &self,
        request: &LoadRequest,
    ) -> impl Future<Output = Result<LoadValue, LoadError>> + Send {
        assert_eq!(request.key().to_string(), "system:database-status");
        self.origin_loads.fetch_add(1, Ordering::SeqCst);
        async {
            Ok(LoadValue::typed(loader::DatabaseStatus {
                driver: "SQLite",
                version: "9.9-test".to_string(),
            }))
        }
    }
}

async fn render_request(loader: Arc<InstrumentedLoader>) -> String {
    let resolver = DataResolver::request_scope(loader);
    let mut cx = WebContext::with_loader(resolver);
    WebRender::render(components::DatabaseBadge, &mut cx)
        .resolve()
        .await
        .unwrap();
    WebRender::render(components::DatabaseCard, &mut cx)
        .resolve()
        .await
        .unwrap();
    cx.into_output().into_string()
}

#[tokio::test]
async fn two_components_deduplicate_one_keyed_load_per_request() {
    let origin_loads = Arc::new(AtomicUsize::new(0));
    let loader = Arc::new(InstrumentedLoader {
        origin_loads: Arc::clone(&origin_loads),
    });

    let first = render_request(Arc::clone(&loader)).await;
    assert!(first.contains("data-database-badge"));
    assert!(first.contains("data-database-card"));
    assert!(first.contains("9.9-test"));
    assert_eq!(origin_loads.load(Ordering::SeqCst), 1);

    let second = render_request(loader).await;
    assert!(second.contains("data-database-badge"));
    assert_eq!(origin_loads.load(Ordering::SeqCst), 2);
}

#[tokio::test]
async fn markdown_exposes_the_same_database_value_and_deduplicates_its_children() {
    let origin_loads = Arc::new(AtomicUsize::new(0));
    let loader = Arc::new(InstrumentedLoader {
        origin_loads: Arc::clone(&origin_loads),
    });
    let resolver = DataResolver::request_scope(loader);
    let mut cx = WebContext::with_loader(resolver);
    MdRender::render_md(components::DatabaseBadge, &mut cx)
        .resolve()
        .await
        .unwrap();
    MdRender::render_md(components::DatabaseCard, &mut cx)
        .resolve()
        .await
        .unwrap();
    let markdown = cx.into_output().into_string();
    assert!(markdown.contains(r"9\.9\-test"), "{markdown}");
    assert!(!markdown.contains("<html"));
    assert_eq!(origin_loads.load(Ordering::SeqCst), 1);
}
