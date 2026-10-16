use proa_core::{MdRenderSync, WebContext, WriteBuf, WriteError};
use proa_macros::md_sync;

use super::Card;

impl<L: proa_core::DataLoader, B: WriteBuf> MdRenderSync<L, B> for Card {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        md_sync! { { self.eyebrow } "\n\n## " { self.title } "\n\n" { self.body } }.render_md(cx)
    }
}
