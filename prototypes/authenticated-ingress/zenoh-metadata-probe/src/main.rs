use std::{
    error::Error,
    fmt::{self, Display, Formatter},
    future::IntoFuture,
    net::TcpListener,
    time::Duration,
};

use serde::Serialize;
use tokio::time::{sleep, timeout};
use zenoh::{config::Config, sample::SourceInfo, Session};

const OPERATION_TIMEOUT: Duration = Duration::from_secs(10);
const DECLARATION_SETTLE: Duration = Duration::from_millis(250);
const PUBSUB_KEY: &str = "ncp/prototype/zenoh/source-info";
const QUERY_KEY: &str = "ncp/prototype/zenoh/query-source-info";
const LIVELINESS_KEY: &str = "ncp/prototype/zenoh/liveliness";

#[derive(Debug)]
struct ProbeError(String);

impl Display for ProbeError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl Error for ProbeError {}

#[derive(Debug, Serialize)]
struct Observations {
    explicit_tcp_peers_enumerate_each_other: bool,
    pubsub_sender_chose_receiver_entity_id: bool,
    pubsub_sender_chose_sequence: bool,
    pubsub_omission_remained_none: bool,
    query_sender_chose_receiver_entity_id: bool,
    query_sender_chose_sequence: bool,
    reply_sender_chose_requester_entity_id: bool,
    reply_sender_chose_sequence: bool,
    query_omission_remained_none: bool,
    reply_omission_remained_none: bool,
    reply_replier_id_was_present: bool,
    liveliness_put_source_was_none: bool,
    liveliness_query_source_was_none: bool,
    liveliness_query_replier_id_was_none: bool,
    liveliness_delete_source_was_none: bool,
}

#[derive(Debug, Serialize)]
struct ClaimBoundary {
    live_probe_proves_api_absence: bool,
    source_info_authenticates_identity: bool,
    zenoh_id_is_certificate_principal: bool,
    production_secure_is_available: bool,
    external_gate_satisfied: bool,
}

#[derive(Debug, Serialize)]
struct ProbeReport {
    schema: &'static str,
    zenoh_version: &'static str,
    transport: &'static str,
    observations: Observations,
    claim_boundary: ClaimBoundary,
}

async fn resolve<T, E, I>(label: &str, resolvable: I) -> Result<T, ProbeError>
where
    E: Display,
    I: IntoFuture<Output = Result<T, E>>,
{
    timeout(OPERATION_TIMEOUT, resolvable.into_future())
        .await
        .map_err(|_| ProbeError(format!("{label} timed out")))?
        .map_err(|error| ProbeError(format!("{label} failed: {error}")))
}

fn reserve_loopback_port() -> Result<u16, ProbeError> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| ProbeError(format!("cannot reserve loopback port: {error}")))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| ProbeError(format!("cannot read reserved port: {error}")))
}

fn peer_config(listen: &[String], connect: &[String]) -> Result<Config, ProbeError> {
    let mut config = Config::default();
    let entries = [
        ("mode", serde_json::json!("peer")),
        ("listen/endpoints", serde_json::json!(listen)),
        ("connect/endpoints", serde_json::json!(connect)),
        ("scouting/multicast/enabled", serde_json::json!(false)),
        ("scouting/gossip/enabled", serde_json::json!(false)),
    ];
    for (key, value) in entries {
        config
            .insert_json5(key, &value.to_string())
            .map_err(|error| ProbeError(format!("cannot set Zenoh config {key}: {error}")))?;
    }
    Ok(config)
}

async fn open_pair() -> Result<(Session, Session), ProbeError> {
    let port = reserve_loopback_port()?;
    let endpoint = format!("tcp/127.0.0.1:{port}");
    let listener_config = peer_config(std::slice::from_ref(&endpoint), &[])?;
    let listener = resolve("open listening peer", zenoh::open(listener_config)).await?;
    let connector_config = peer_config(&[], std::slice::from_ref(&endpoint))?;
    let connector = resolve("open connecting peer", zenoh::open(connector_config)).await?;
    Ok((listener, connector))
}

async fn run_probe() -> Result<ProbeReport, ProbeError> {
    zenoh::init_log_from_env_or("error");
    let (requester, responder) = open_pair().await?;
    let requester_id = requester.id();
    let responder_id = responder.id();
    if requester_id == responder_id {
        return Err(ProbeError(
            "Zenoh peers unexpectedly share one entity ID".into(),
        ));
    }

    let requester_zid = requester.info().zid().await;
    let responder_zid = responder.info().zid().await;
    let requester_peers: Vec<_> = requester.info().peers_zid().await.collect();
    let responder_peers: Vec<_> = responder.info().peers_zid().await.collect();
    let explicit_tcp_peers_enumerate_each_other =
        requester_peers.contains(&responder_zid) && responder_peers.contains(&requester_zid);
    if !explicit_tcp_peers_enumerate_each_other {
        return Err(ProbeError(
            "explicit TCP peers did not enumerate each other's Zenoh IDs".into(),
        ));
    }

    let subscriber = resolve(
        "declare subscriber",
        responder.declare_subscriber(PUBSUB_KEY),
    )
    .await?;
    let publisher = resolve("declare publisher", requester.declare_publisher(PUBSUB_KEY)).await?;
    sleep(DECLARATION_SETTLE).await;

    const PUBSUB_SEQUENCE: u32 = 424_242;
    resolve(
        "publish chosen SourceInfo",
        publisher
            .put("chosen-source")
            .source_info(SourceInfo::new(responder_id, PUBSUB_SEQUENCE)),
    )
    .await?;
    let chosen_sample = resolve("receive chosen SourceInfo", subscriber.recv_async()).await?;
    let chosen_pubsub_source = chosen_sample
        .source_info()
        .ok_or_else(|| ProbeError("chosen pub/sub SourceInfo was absent".into()))?;
    let pubsub_sender_chose_receiver_entity_id = chosen_pubsub_source.source_id() == &responder_id
        && chosen_pubsub_source.source_id() != &requester_id;
    let pubsub_sender_chose_sequence = chosen_pubsub_source.source_sn() == PUBSUB_SEQUENCE;

    resolve("publish without SourceInfo", publisher.put("no-source")).await?;
    let no_source_sample = resolve("receive no SourceInfo", subscriber.recv_async()).await?;
    let pubsub_omission_remained_none = no_source_sample.source_info().is_none();

    let queryable = resolve("declare queryable", responder.declare_queryable(QUERY_KEY)).await?;
    sleep(DECLARATION_SETTLE).await;

    const QUERY_SEQUENCE: u32 = 515_151;
    let replies = resolve(
        "send query with chosen SourceInfo",
        requester
            .get(QUERY_KEY)
            .source_info(SourceInfo::new(responder_id, QUERY_SEQUENCE)),
    )
    .await?;
    let query = resolve(
        "receive query with chosen SourceInfo",
        queryable.recv_async(),
    )
    .await?;
    let chosen_query_source = query
        .source_info()
        .ok_or_else(|| ProbeError("chosen query SourceInfo was absent".into()))?;
    let query_sender_chose_receiver_entity_id = chosen_query_source.source_id() == &responder_id
        && chosen_query_source.source_id() != &requester_id;
    let query_sender_chose_sequence = chosen_query_source.source_sn() == QUERY_SEQUENCE;

    const REPLY_SEQUENCE: u32 = 616_161;
    resolve(
        "reply with chosen SourceInfo",
        query
            .reply(QUERY_KEY, "chosen-reply-source")
            .source_info(SourceInfo::new(requester_id, REPLY_SEQUENCE)),
    )
    .await?;
    drop(query);
    let reply = resolve("receive reply with chosen SourceInfo", replies.recv_async()).await?;
    let reply_replier_id_was_present = reply.replier_id().is_some();
    let reply_sample = reply
        .result()
        .map_err(|error| ProbeError(format!("query returned an error reply: {error}")))?;
    let chosen_reply_source = reply_sample
        .source_info()
        .ok_or_else(|| ProbeError("chosen reply SourceInfo was absent".into()))?;
    let reply_sender_chose_requester_entity_id = chosen_reply_source.source_id() == &requester_id
        && chosen_reply_source.source_id() != &responder_id;
    let reply_sender_chose_sequence = chosen_reply_source.source_sn() == REPLY_SEQUENCE;

    let no_source_replies =
        resolve("send query without SourceInfo", requester.get(QUERY_KEY)).await?;
    let no_source_query =
        resolve("receive query without SourceInfo", queryable.recv_async()).await?;
    let query_omission_remained_none = no_source_query.source_info().is_none();
    resolve(
        "reply without SourceInfo",
        no_source_query.reply(QUERY_KEY, "no-source-reply"),
    )
    .await?;
    drop(no_source_query);
    let no_source_reply = resolve(
        "receive reply without SourceInfo",
        no_source_replies.recv_async(),
    )
    .await?;
    let reply_omission_remained_none = no_source_reply
        .result()
        .map_err(|error| ProbeError(format!("query returned an error reply: {error}")))?
        .source_info()
        .is_none();

    let liveliness_subscriber = resolve(
        "declare liveliness subscriber",
        requester.liveliness().declare_subscriber(LIVELINESS_KEY),
    )
    .await?;
    sleep(DECLARATION_SETTLE).await;
    let token = resolve(
        "declare liveliness token",
        responder.liveliness().declare_token(LIVELINESS_KEY),
    )
    .await?;
    let liveliness_put =
        resolve("receive liveliness put", liveliness_subscriber.recv_async()).await?;
    let liveliness_put_source_was_none = liveliness_put.source_info().is_none();

    let liveliness_replies = resolve(
        "query liveliness token",
        requester.liveliness().get(LIVELINESS_KEY),
    )
    .await?;
    let liveliness_reply = resolve(
        "receive liveliness query reply",
        liveliness_replies.recv_async(),
    )
    .await?;
    let liveliness_query_replier_id_was_none = liveliness_reply.replier_id().is_none();
    let liveliness_query_source_was_none = liveliness_reply
        .result()
        .map_err(|error| ProbeError(format!("liveliness returned an error reply: {error}")))?
        .source_info()
        .is_none();

    resolve("undeclare liveliness token", token.undeclare()).await?;
    let liveliness_delete = resolve(
        "receive liveliness delete",
        liveliness_subscriber.recv_async(),
    )
    .await?;
    let liveliness_delete_source_was_none = liveliness_delete.source_info().is_none();

    let required = [
        pubsub_sender_chose_receiver_entity_id,
        pubsub_sender_chose_sequence,
        pubsub_omission_remained_none,
        query_sender_chose_receiver_entity_id,
        query_sender_chose_sequence,
        reply_sender_chose_requester_entity_id,
        reply_sender_chose_sequence,
        query_omission_remained_none,
        reply_omission_remained_none,
        reply_replier_id_was_present,
        liveliness_put_source_was_none,
        liveliness_query_source_was_none,
        liveliness_query_replier_id_was_none,
        liveliness_delete_source_was_none,
    ];
    if required.contains(&false) {
        return Err(ProbeError(
            "one or more required metadata observations did not hold".into(),
        ));
    }

    drop(liveliness_subscriber);
    drop(queryable);
    drop(publisher);
    drop(subscriber);
    resolve("close responding peer", responder.close()).await?;
    sleep(DECLARATION_SETTLE).await;
    resolve("close requesting peer", requester.close()).await?;

    Ok(ProbeReport {
        schema: "ncp.prototype.zenoh-metadata-probe.v1",
        zenoh_version: "1.9.0",
        transport: "explicit-loopback-tcp-no-tls",
        observations: Observations {
            explicit_tcp_peers_enumerate_each_other,
            pubsub_sender_chose_receiver_entity_id,
            pubsub_sender_chose_sequence,
            pubsub_omission_remained_none,
            query_sender_chose_receiver_entity_id,
            query_sender_chose_sequence,
            reply_sender_chose_requester_entity_id,
            reply_sender_chose_sequence,
            query_omission_remained_none,
            reply_omission_remained_none,
            reply_replier_id_was_present,
            liveliness_put_source_was_none,
            liveliness_query_source_was_none,
            liveliness_query_replier_id_was_none,
            liveliness_delete_source_was_none,
        },
        claim_boundary: ClaimBoundary {
            live_probe_proves_api_absence: false,
            source_info_authenticates_identity: false,
            zenoh_id_is_certificate_principal: false,
            production_secure_is_available: false,
            external_gate_satisfied: false,
        },
    })
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<(), Box<dyn Error>> {
    let report = run_probe().await?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn exact_zenoh_metadata_boundary_is_observed() {
        let report = run_probe().await.expect("live metadata probe should pass");
        assert!(report.observations.pubsub_sender_chose_receiver_entity_id);
        assert!(report.observations.query_sender_chose_receiver_entity_id);
        assert!(report.observations.reply_sender_chose_requester_entity_id);
        assert!(report.observations.reply_replier_id_was_present);
        assert!(!report.claim_boundary.live_probe_proves_api_absence);
        assert!(!report.claim_boundary.production_secure_is_available);
    }
}
