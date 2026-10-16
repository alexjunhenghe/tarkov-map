use std::{
    future::Future,
    sync::atomic::{AtomicUsize, Ordering},
};

use proa_core::{DataLoader, LoadError, LoadKey, LoadRequest, LoadValue};
use sqlx::SqlitePool;

#[derive(Debug)]
pub struct DatabaseStatus {
    pub driver: &'static str,
    pub version: String,
}

pub fn database_status_key() -> LoadKey {
    LoadKey::named("system", "database-status")
}

pub struct AppLoader {
    pub db: SqlitePool,
    origin_loads: AtomicUsize,
}

impl AppLoader {
    pub fn new(db: SqlitePool) -> Self {
        Self {
            db,
            origin_loads: AtomicUsize::new(0),
        }
    }
}

impl DataLoader for AppLoader {
    fn load(
        &self,
        request: &LoadRequest,
    ) -> impl Future<Output = Result<LoadValue, LoadError>> + Send {
        let db = self.db.clone();
        let key = request.key().to_string();
        self.origin_loads.fetch_add(1, Ordering::Relaxed);
        async move {
            match key.as_str() {
                "system:database-status" => {
                    let version = sqlx::query_scalar::<_, String>("SELECT sqlite_version()")
                        .fetch_one(&db)
                        .await
                        .map_err(|error| LoadError::custom(error.to_string()))?;
                    Ok(LoadValue::typed(DatabaseStatus {
                        driver: "SQLite",
                        version,
                    }))
                }
                _ => Err(LoadError::custom(format!("unknown load key: {key}"))),
            }
        }
    }
}
