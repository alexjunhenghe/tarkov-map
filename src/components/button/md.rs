use proa_core::{MdRenderSync, WebContext, WriteBuf, WriteError};
use proa_macros::md_sync;

use super::Button;

impl<L: proa_core::DataLoader, B: WriteBuf> MdRenderSync<L, B> for Button {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        if self.href.is_some() {
            let href = self.href.unwrap_or_default();
            md_sync! { "[" { self.label } "](" { href } ")" }.render_md(cx)
        } else {
            proa_core::MdRenderSync::render_md(self.label, cx)
        }
    }
}
