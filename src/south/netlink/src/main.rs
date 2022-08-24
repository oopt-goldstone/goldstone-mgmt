mod server;
mod xpath;

use std::sync::{Arc, Mutex};

use anyhow::Context;
use clap::Parser;
use tokio::signal;

use sysrepo2::connection::Connection;
use sysrepo2::types::ConnectionOptions;

use crate::server::Server;

#[derive(Parser, Debug)]
#[clap(author, version, about, long_about = None)]
struct Args {
    /// Name of the model to handle
    #[clap(short, long, value_parser, default_value = "goldstone-interfaces")]
    model: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();

    env_logger::init();
    let conn =
        Connection::new(ConnectionOptions::DEFAULT).context("Failed to create connection")?;
    let conn = Arc::new(Mutex::new(conn));
    Server::new(&conn, &args.model)?;

    signal::ctrl_c().await?;

    Ok(())
}
