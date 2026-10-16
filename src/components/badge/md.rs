use proa_core::{MdRenderSync, WebContext, WriteBuf, WriteError};

use super::Badge;

impl<L: proa_core::DataLoader, B: WriteBuf> MdRenderSync<L, B> for Badge {
    fn render_md(self, cx: &mut WebContext<L, B>) -> Result<(), WriteError> {
        proa_core::MdRenderSync::render_md(self.label, cx)
    }
}
