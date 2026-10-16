use proa_core::{DataLoader, WebContext, WebRenderSync, WriteError};
use proa_macros::html_sync;

use super::recipe::button_classes;

#[derive(Debug, Clone, Copy)]
pub struct Button {
    pub label: &'static str,
    pub href: Option<&'static str>,
    pub class: Option<&'static str>,
}

impl Button {
    pub const fn link(label: &'static str, href: &'static str) -> Self {
        Self {
            label,
            href: Some(href),
            class: None,
        }
    }
}

impl<L: DataLoader> WebRenderSync<L> for Button {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        let classes = button_classes().add_opt(self.class);
        if self.href.is_some() {
            let href = self.href.unwrap_or_default();
            html_sync! {
                <a data-button href={href} class={classes}>{self.label}</a>
            }
            .render(cx)
        } else {
            html_sync! {
                <button data-button class={classes}>{self.label}</button>
            }
            .render(cx)
        }
    }
}
