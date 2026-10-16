use proa_core::{DataLoader, WebContext, WebRenderSync, WriteError};
use proa_macros::html_sync;

use super::recipe::card_classes;

#[derive(Debug, Clone, Copy)]
pub struct Card {
    pub eyebrow: &'static str,
    pub title: &'static str,
    pub body: &'static str,
    pub class: Option<&'static str>,
}

impl<L: DataLoader> WebRenderSync<L> for Card {
    fn render(self, cx: &mut WebContext<L>) -> Result<(), WriteError> {
        let classes = card_classes().add_opt(self.class);
        html_sync! {
            <article data-card class={classes}>
                <p class="card-eyebrow">{self.eyebrow}</p>
                <h2>{self.title}</h2>
                <p>{self.body}</p>
            </article>
        }
        .render(cx)
    }
}
