use std::future::Future;

use proa_core::{DataLoader, RenderOutcome, WebContext, WebRender, WebRenderSync, WriteError};
use proa_macros::html_sync;

use crate::loader::{database_status_key, DatabaseStatus};

#[derive(Debug, Clone, Copy)]
pub struct DatabaseBadge;

impl<L: DataLoader> WebRender<L> for DatabaseBadge {
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
                    <span data-database-badge data-driver={status.driver} class="status-pill">
                        <span class="status-dot"></span>
                        {status.driver}
                        " "
                        {status.version.as_str()}
                    </span>
                },
                cx,
            )
        })
    }
}

impl<L: DataLoader> proa_core::MdRender<L> for DatabaseBadge {
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
                    {status.driver} " "
                    {status.version.as_str()}
                },
                cx,
            )
        })
    }
}
