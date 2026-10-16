use proa_core::{DataLoader, WebContext, WebRenderSync, WriteError};
use proa_macros::html_sync;

use super::recipe::badge_classes;

#[derive(Debug, Clone, Copy)]
pub struct Badge {
    pub label: &'static str,
    pub class: Option<&'static str>,
}

impl Badge {
    pub const fn new(label: &'static str) -> Self {
        Self { label, class: None }
    }
}

impl<L: DataLoader> WebRenderSync<L> for Badge {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        let classes = badge_classes().add_opt(self.class);
        html_sync! {
            <span data-badge class={classes}>{self.label}</span>
        }
        .render(cx)
    }
}
