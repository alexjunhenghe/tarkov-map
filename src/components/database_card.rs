use std::future::Future;

use proa_core::{DataLoader, RenderOutcome, WebContext, WebRender, WebRenderSync, WriteError};
use proa_macros::html_sync;

use crate::loader::{database_status_key, DatabaseStatus};

#[derive(Debug, Clone, Copy)]
pub struct DatabaseCard;

impl<L: DataLoader> WebRender<L> for DatabaseCard {
    fn render(
        self,
        cx: &mut WebContext<L>,
    ) -> RenderOutcome<impl Future<Output = Result<(), WriteError>>> {
        RenderOutcome::pending(async move {
            let status = cx
                .load_typed::<DatabaseStatus>(database_status_key())
                .await?;
            WebRenderSync::render(
                html_sync! {
                    <article data-database-card class="metric-card">
                        <p class="metric-label">"DATA ORIGIN"</p>
                        <p class="metric-value">{status.driver}</p>
                        <p class="metric-note">
                            "Two component requests resolve through one keyed origin query."
                        </p>
                    </article>
                },
                cx,
            )
        })
    }
}

impl<L: DataLoader> proa_core::MdRender<L> for DatabaseCard {
    fn render_md(
        self,
        cx: &mut WebContext<L>,
    ) -> RenderOutcome<impl Future<Output = Result<(), WriteError>>> {
        RenderOutcome::pending(async move {
            let status = cx
                .load_typed::<DatabaseStatus>(database_status_key())
                .await?;
            proa_core::MdRenderSync::render_md(
                proa_macros::md_sync! {
                    "## " "DATA ORIGIN"
                    "\n\n" {status.driver}
                    "\n\n" "Two component requests resolve through one keyed origin query."
                },
                cx,
            )
        })
    }
}
