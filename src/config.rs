use std::net::{IpAddr, SocketAddr};

pub struct Config {
    pub address: SocketAddr,
    pub database_url: String,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        dotenvy::dotenv().ok();
        let host: IpAddr = std::env::var("PROA_HOST")
            .unwrap_or_else(|_| "127.0.0.1".to_string())
            .parse()?;
        let port = std::env::var("PORT")
            .unwrap_or_else(|_| "3000".to_string())
            .parse()?;
        let database_url = std::env::var("DATABASE_URL")
            .unwrap_or_else(|_| "sqlite://data/tarkov-map-app.db".to_string());
        Ok(Self {
            address: SocketAddr::new(host, port),
            database_url,
        })
    }
}
