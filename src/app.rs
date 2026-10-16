use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub db: sqlx::SqlitePool,
    pub loader: Arc<crate::loader::AppLoader>,
}
