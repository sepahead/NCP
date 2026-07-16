use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Barrier,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use ncp_core::{Plane, PrincipalRole};
use ncp_tls_terminating_ingress_prototype::{
    build_tls13_server_config, EndpointProfile, ErrorCode, IngressLimits, ManifestStore,
    RotationOutcome, TlsIngress, VolatileReplayProbe, ALPN_PROTOCOL, MANIFEST_SCHEMA,
};
use rcgen::{
    BasicConstraints, Certificate, CertificateParams, ExtendedKeyUsagePurpose, IsCa, Issuer,
    KeyPair, KeyUsagePurpose,
};
use rustls::{
    client::Resumption,
    pki_types::{PrivateKeyDer, PrivatePkcs8KeyDer, ServerName},
    version, ClientConfig, RootCertStore,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use time::{Duration as TimeDuration, OffsetDateTime};
use tokio::{
    io::{AsyncWriteExt, Interest},
    net::{TcpListener, TcpStream},
    task::JoinHandle,
};
use tokio_rustls::TlsConnector;

const ROUTE: &str = "ncp/session/open";
const CLASS: &str = "open_session";
const PRINCIPAL: &str = "controller-principal-1";
const ENTITY: &str = "pid-controller-1";

struct IdentityMaterial {
    certificate: Certificate,
    key: KeyPair,
}

struct TestPki {
    root: Certificate,
    root_issuer: Issuer<'static, KeyPair>,
    server: IdentityMaterial,
    client: IdentityMaterial,
}

fn validity() -> (OffsetDateTime, OffsetDateTime) {
    let now = OffsetDateTime::now_utc();
    (now - TimeDuration::days(1), now + TimeDuration::days(1))
}

fn root_ca(name: &str) -> (Certificate, Issuer<'static, KeyPair>) {
    let mut params = CertificateParams::new(Vec::<String>::new()).unwrap();
    let (not_before, not_after) = validity();
    params.not_before = not_before;
    params.not_after = not_after;
    params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
    params
        .distinguished_name
        .push(rcgen::DnType::CommonName, name);
    params.key_usages = vec![
        KeyUsagePurpose::DigitalSignature,
        KeyUsagePurpose::KeyCertSign,
        KeyUsagePurpose::CrlSign,
    ];
    let key = KeyPair::generate().unwrap();
    let certificate = params.self_signed(&key).unwrap();
    (certificate, Issuer::new(params, key))
}

fn leaf(
    name: &str,
    usage: Option<ExtendedKeyUsagePurpose>,
    issuer: &Issuer<'_, KeyPair>,
    not_before: OffsetDateTime,
    not_after: OffsetDateTime,
) -> IdentityMaterial {
    let mut params = CertificateParams::new(vec![name.to_owned()]).unwrap();
    params.not_before = not_before;
    params.not_after = not_after;
    params
        .distinguished_name
        .push(rcgen::DnType::CommonName, name);
    params.key_usages = vec![KeyUsagePurpose::DigitalSignature];
    if let Some(usage) = usage {
        params.extended_key_usages.push(usage);
    }
    let key = KeyPair::generate().unwrap();
    let certificate = params.signed_by(&key, issuer).unwrap();
    IdentityMaterial { certificate, key }
}

fn pki() -> TestPki {
    let (root, root_issuer) = root_ca("NCP prototype root");
    let (not_before, not_after) = validity();
    let server = leaf(
        "localhost",
        Some(ExtendedKeyUsagePurpose::ServerAuth),
        &root_issuer,
        not_before,
        not_after,
    );
    let client = leaf(
        "prototype-client",
        Some(ExtendedKeyUsagePurpose::ClientAuth),
        &root_issuer,
        not_before,
        not_after,
    );
    TestPki {
        root,
        root_issuer,
        server,
        client,
    }
}

fn root_store(certificate: &Certificate) -> RootCertStore {
    let mut roots = RootCertStore::empty();
    roots.add(certificate.der().clone()).unwrap();
    roots
}

fn private_key(key: &KeyPair) -> PrivateKeyDer<'static> {
    PrivatePkcs8KeyDer::from(key.serialize_der()).into()
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn manifest_bytes(
    generation: u64,
    fingerprint: &str,
    principal: &str,
    entity: &str,
    route: &str,
) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema": MANIFEST_SCHEMA,
        "generation": generation,
        "default_deny": true,
        "principals": [{
            "principal_id": principal,
            "entity_id": entity,
            "role": "commander",
            "certificate_sha256": fingerprint,
            "grants": [{
                "route": route,
                "plane": "control",
                "message_class": CLASS
            }]
        }]
    }))
    .unwrap()
}

fn payload(principal: &str, entity: &str, role: &str, plane: &str) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "ncp_version": "1.0",
        "kind": "open_session",
        "session_id": "prototype-open-1",
        "network": {
            "kind": "builtin",
            "ref": "iaf_cond_exp",
            "population_sizes": {"feat": 4}
        },
        "record": {"targets": []},
        "stimulus": {"targets": []},
        "sim": {"dt_ms": 0.1, "chunk_ms": 10.0, "mode": "stream"},
        "bindings": [],
        "contract_hash": "163acc57d8a62b66",
        "identity": {
            "principal_id": principal,
            "entity_id": entity,
            "role": role,
            "plane": plane
        },
        "security_profile": "production-secure",
        "security_state_digest":
            "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab",
        "gateway_permitted": false
    }))
    .unwrap()
}

fn client_config(pki: &TestPki, identity: Option<&IdentityMaterial>) -> Arc<ClientConfig> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let builder = ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .unwrap()
        .with_root_certificates(root_store(&pki.root));
    let mut config = match identity {
        Some(identity) => builder
            .with_client_auth_cert(
                vec![identity.certificate.der().clone()],
                private_key(&identity.key),
            )
            .unwrap(),
        None => builder.with_no_client_auth(),
    };
    config.alpn_protocols = vec![ALPN_PROTOCOL.to_vec()];
    config.resumption = Resumption::disabled();
    config.enable_early_data = false;
    Arc::new(config)
}

fn client_config_with_chain(
    root: &Certificate,
    chain: Vec<rustls::pki_types::CertificateDer<'static>>,
    key: &KeyPair,
) -> Arc<ClientConfig> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let mut config = ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .unwrap()
        .with_root_certificates(root_store(root))
        .with_client_auth_cert(chain, private_key(key))
        .unwrap();
    config.alpn_protocols = vec![ALPN_PROTOCOL.to_vec()];
    config.resumption = Resumption::disabled();
    config.enable_early_data = false;
    Arc::new(config)
}

fn build_ingress(
    pki: &TestPki,
    manifests: Arc<ManifestStore>,
    limits: IngressLimits,
) -> TlsIngress {
    let server = build_tls13_server_config(
        root_store(&pki.root),
        vec![pki.server.certificate.der().clone()],
        private_key(&pki.server.key),
    )
    .unwrap();
    TlsIngress::new(
        server,
        manifests,
        EndpointProfile::new(ROUTE, Plane::Control, CLASS).unwrap(),
        limits,
    )
    .unwrap()
}

async fn spawn_server(
    ingress: Arc<TlsIngress>,
) -> (
    std::net::SocketAddr,
    JoinHandle<
        Result<
            ncp_tls_terminating_ingress_prototype::AuthenticatedMessage,
            ncp_tls_terminating_ingress_prototype::IngressError,
        >,
    >,
) {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let handle = tokio::spawn(async move { ingress.accept_one(&listener).await });
    (address, handle)
}

async fn connect(
    address: std::net::SocketAddr,
    config: Arc<ClientConfig>,
) -> Result<tokio_rustls::client::TlsStream<TcpStream>, Box<dyn std::error::Error>> {
    let stream = TcpStream::connect(address).await?;
    let name = ServerName::try_from("localhost")?.to_owned();
    Ok(TlsConnector::from(config).connect(name, stream).await?)
}

async fn write_frame(
    stream: &mut tokio_rustls::client::TlsStream<TcpStream>,
    payload: &[u8],
) -> Result<(), Box<dyn std::error::Error>> {
    stream
        .write_all(&(payload.len() as u32).to_be_bytes())
        .await?;
    stream.write_all(payload).await?;
    stream.shutdown().await?;
    Ok(())
}

fn store_for(pki: &TestPki) -> Arc<ManifestStore> {
    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let bytes = manifest_bytes(1, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    let digest = sha256_hex(&bytes);
    Arc::new(ManifestStore::new(&bytes, &digest).unwrap())
}

#[tokio::test]
async fn accepts_exact_tls_manifest_and_payload_binding() {
    let pki = pki();
    let manifests = store_for(&pki);
    let ingress = Arc::new(build_ingress(
        &pki,
        Arc::clone(&manifests),
        IngressLimits::default(),
    ));
    let (address, server) = spawn_server(ingress).await;
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    write_frame(&mut client, &bytes).await.unwrap();
    let message = server.await.unwrap().unwrap();
    assert_eq!(message.payload(), bytes);
    assert_eq!(message.context().principal_id(), PRINCIPAL);
    assert_eq!(message.context().entity_id(), ENTITY);
    assert_eq!(message.context().role(), PrincipalRole::Commander);
    assert_eq!(message.context().plane(), Plane::Control);
    assert_eq!(message.context().route(), ROUTE);
    assert_eq!(message.context().message_class(), CLASS);
    assert_eq!(message.context().manifest_generation(), 1);
    assert_ne!(message.context().boot_id(), &[0; 16]);
}

#[tokio::test]
async fn debug_output_redacts_payload_bytes_and_retains_their_digest() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let mut value: Value =
        serde_json::from_slice(&payload(PRINCIPAL, ENTITY, "commander", "control")).unwrap();
    value["session_id"] = json!("secret-payload-sentinel");
    let bytes = serde_json::to_vec(&value).unwrap();
    let (address, server) = spawn_server(ingress).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    write_frame(&mut client, &bytes).await.unwrap();
    let message = server.await.unwrap().unwrap();
    let debug = format!("{message:?}");
    assert!(!debug.contains("secret-payload-sentinel"));
    assert!(debug.contains(message.payload_sha256()));
}

#[tokio::test]
async fn live_result() {
    let started = Instant::now();
    let pki = pki();
    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let manifest = manifest_bytes(1, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    let manifest_digest = sha256_hex(&manifest);
    let manifests = Arc::new(ManifestStore::new(&manifest, &manifest_digest).unwrap());
    let ingress = Arc::new(build_ingress(&pki, manifests, IngressLimits::default()));
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");
    let mut replay = VolatileReplayProbe::default();
    let mut duplicate_observations = Vec::new();

    for _ in 0..2 {
        let (address, server) = spawn_server(Arc::clone(&ingress)).await;
        let mut client = connect(address, client_config(&pki, Some(&pki.client)))
            .await
            .unwrap();
        write_frame(&mut client, &bytes).await.unwrap();
        let message = server.await.unwrap().unwrap();
        assert_eq!(message.payload_sha256(), sha256_hex(message.payload()));
        duplicate_observations.push(replay.observe(message).unwrap().duplicate_exact_message());
    }

    println!(
        "NCP_TLS_INGRESS_RESULT={}",
        serde_json::to_string(&json!({
            "schema": "ncp.prototype.tls-terminating-ingress-result.v1",
            "scope": "quarantined-local-feasibility",
            "tls": {
                "version": "1.3",
                "provider": "ring",
                "client_certificate_required": true,
                "alpn": std::str::from_utf8(ALPN_PROTOCOL).unwrap(),
                "tickets_sent": 0,
                "resumption_accepted": false,
                "zero_rtt_accepted": false
            },
            "binding": {
                "exact_leaf_der_sha256": true,
                "manifest_default_deny": true,
                "payload_identity_exact_match": true,
                "manifest_generation": 1,
                "same_immutable_payload": true,
                "context_serialized": false
            },
            "replay_probe": {
                "ingress_admitted_identical_messages": 2,
                "duplicate_observations": duplicate_observations,
                "durable": false,
                "affects_admission": false
            },
            "resources": {
                "manifest_bytes": manifest.len(),
                "manifest_limit_bytes":
                    ncp_tls_terminating_ingress_prototype::MAX_MANIFEST_BYTES,
                "payload_bytes": bytes.len(),
                "frame_limit_bytes": ncp_core::bounded_json::MAX_FRAME_BYTES,
                "connections": 2,
                "elapsed_microseconds_local": started.elapsed().as_micros()
            },
            "claim_boundary": {
                "production_security_proved": false,
                "live_rotation_revocation_gate_satisfied": false,
                "authorization_granted": false,
                "plant_authority_granted": false,
                "release_gate_satisfied": false
            }
        }))
        .unwrap()
    );
}

#[tokio::test]
async fn duplicate_authentication_is_not_replay_authorization() {
    let pki = pki();
    let manifests = store_for(&pki);
    let ingress = Arc::new(build_ingress(&pki, manifests, IngressLimits::default()));
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");
    let mut replay = VolatileReplayProbe::default();

    for expected_duplicate in [false, true] {
        let (address, server) = spawn_server(Arc::clone(&ingress)).await;
        let mut client = connect(address, client_config(&pki, Some(&pki.client)))
            .await
            .unwrap();
        write_frame(&mut client, &bytes).await.unwrap();
        let message = server.await.unwrap().unwrap();
        assert_eq!(
            replay.observe(message).unwrap().duplicate_exact_message(),
            expected_duplicate
        );
    }

    let mut restarted = VolatileReplayProbe::default();
    let (address, server) = spawn_server(ingress).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    write_frame(&mut client, &bytes).await.unwrap();
    assert!(!restarted
        .observe(server.await.unwrap().unwrap())
        .unwrap()
        .duplicate_exact_message());
}

#[tokio::test]
async fn false_inner_identity_and_wrong_endpoint_grant_reject() {
    let pki = pki();
    let manifests = store_for(&pki);
    let ingress = Arc::new(build_ingress(&pki, manifests, IngressLimits::default()));
    let (address, server) = spawn_server(ingress).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    write_frame(
        &mut client,
        &payload("attacker", ENTITY, "commander", "control"),
    )
    .await
    .unwrap();
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::IdentityMismatch
    );

    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let bytes = manifest_bytes(1, &fingerprint, PRINCIPAL, ENTITY, "ncp/other");
    let digest = sha256_hex(&bytes);
    let manifests = Arc::new(ManifestStore::new(&bytes, &digest).unwrap());
    let ingress = Arc::new(build_ingress(&pki, manifests, IngressLimits::default()));
    let (address, server) = spawn_server(ingress).await;
    let result = connect(address, client_config(&pki, Some(&pki.client))).await;
    if let Ok(mut client) = result {
        let _ = write_frame(
            &mut client,
            &payload(PRINCIPAL, ENTITY, "commander", "control"),
        )
        .await;
    }
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::ManifestDenied
    );
}

#[tokio::test]
async fn mandatory_client_certificate_and_explicit_server_only_eku_reject() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let result = connect(address, client_config(&pki, None)).await;
    if let Ok(mut stream) = result {
        let _ = write_frame(
            &mut stream,
            &payload(PRINCIPAL, ENTITY, "commander", "control"),
        )
        .await;
    }
    assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);

    let (not_before, not_after) = validity();
    let wrong_eku = leaf(
        "wrong-eku",
        Some(ExtendedKeyUsagePurpose::ServerAuth),
        &pki.root_issuer,
        not_before,
        not_after,
    );
    let (address, server) = spawn_server(ingress).await;
    let result = connect(address, client_config(&pki, Some(&wrong_eku))).await;
    if let Ok(mut stream) = result {
        let _ = write_frame(
            &mut stream,
            &payload(PRINCIPAL, ENTITY, "commander", "control"),
        )
        .await;
    }
    assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);
}

#[tokio::test]
async fn absent_eku_is_observed_as_webpki_unrestricted_not_explicit_client_auth() {
    let mut pki = pki();
    let (not_before, not_after) = validity();
    pki.client = leaf("absent-eku", None, &pki.root_issuer, not_before, not_after);
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let (address, server) = spawn_server(ingress).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    write_frame(
        &mut client,
        &payload(PRINCIPAL, ENTITY, "commander", "control"),
    )
    .await
    .unwrap();
    assert!(server.await.unwrap().is_ok());
}

#[tokio::test]
async fn alpn_mismatch_and_plaintext_are_unavailable() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut config = client_config(&pki, Some(&pki.client));
    Arc::get_mut(&mut config).unwrap().alpn_protocols = vec![b"alternate/1".to_vec()];
    let result = connect(address, config).await;
    if let Ok(mut stream) = result {
        let _ = write_frame(
            &mut stream,
            &payload(PRINCIPAL, ENTITY, "commander", "control"),
        )
        .await;
    }
    assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);

    let (address, server) = spawn_server(ingress).await;
    let mut plaintext = TcpStream::connect(address).await.unwrap();
    plaintext
        .write_all(b"GET / HTTP/1.0\r\n\r\n")
        .await
        .unwrap();
    plaintext.shutdown().await.unwrap();
    assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);
}

#[tokio::test]
async fn expired_not_yet_valid_and_wrong_ca_clients_reject() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let now = OffsetDateTime::now_utc();
    let expired = leaf(
        "expired",
        Some(ExtendedKeyUsagePurpose::ClientAuth),
        &pki.root_issuer,
        now - TimeDuration::days(3),
        now - TimeDuration::days(2),
    );
    let future = leaf(
        "future",
        Some(ExtendedKeyUsagePurpose::ClientAuth),
        &pki.root_issuer,
        now + TimeDuration::days(2),
        now + TimeDuration::days(3),
    );
    let (_, other_issuer) = root_ca("other root");
    let (not_before, not_after) = validity();
    let wrong_ca = leaf(
        "wrong-ca",
        Some(ExtendedKeyUsagePurpose::ClientAuth),
        &other_issuer,
        not_before,
        not_after,
    );

    for identity in [&expired, &future, &wrong_ca] {
        let (address, server) = spawn_server(Arc::clone(&ingress)).await;
        let result = connect(address, client_config(&pki, Some(identity))).await;
        if let Ok(mut stream) = result {
            let _ = write_frame(
                &mut stream,
                &payload(PRINCIPAL, ENTITY, "commander", "control"),
            )
            .await;
        }
        assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);
    }
}

#[tokio::test]
async fn fingerprints_the_verified_leaf_not_its_intermediate() {
    let (root, root_issuer) = root_ca("chain root");
    let (not_before, not_after) = validity();
    let server_identity = leaf(
        "localhost",
        Some(ExtendedKeyUsagePurpose::ServerAuth),
        &root_issuer,
        not_before,
        not_after,
    );

    let mut intermediate_params = CertificateParams::new(Vec::<String>::new()).unwrap();
    intermediate_params.not_before = not_before;
    intermediate_params.not_after = not_after;
    intermediate_params.is_ca = IsCa::Ca(BasicConstraints::Constrained(0));
    intermediate_params
        .distinguished_name
        .push(rcgen::DnType::CommonName, "chain intermediate");
    intermediate_params.key_usages = vec![
        KeyUsagePurpose::DigitalSignature,
        KeyUsagePurpose::KeyCertSign,
        KeyUsagePurpose::CrlSign,
    ];
    let intermediate_key = KeyPair::generate().unwrap();
    let intermediate_certificate = intermediate_params
        .signed_by(&intermediate_key, &root_issuer)
        .unwrap();
    let intermediate_issuer = Issuer::new(intermediate_params, intermediate_key);
    let client = leaf(
        "chained-client",
        Some(ExtendedKeyUsagePurpose::ClientAuth),
        &intermediate_issuer,
        not_before,
        not_after,
    );
    let pki = TestPki {
        root,
        root_issuer,
        server: server_identity,
        client,
    };
    let manifests = store_for(&pki);
    let ingress = Arc::new(build_ingress(&pki, manifests, IngressLimits::default()));
    let (address, server) = spawn_server(ingress).await;
    let config = client_config_with_chain(
        &pki.root,
        vec![
            pki.client.certificate.der().clone(),
            intermediate_certificate.der().clone(),
        ],
        &pki.client.key,
    );
    let mut client = connect(address, config).await.unwrap();
    write_frame(
        &mut client,
        &payload(PRINCIPAL, ENTITY, "commander", "control"),
    )
    .await
    .unwrap();
    let message = server.await.unwrap().unwrap();
    assert_eq!(
        message.context().leaf_sha256(),
        sha256_hex(pki.client.certificate.der().as_ref())
    );
    assert_ne!(
        message.context().leaf_sha256(),
        sha256_hex(intermediate_certificate.der().as_ref())
    );
}

#[tokio::test]
async fn framing_rejects_oversize_truncation_trailing_and_timeout() {
    let pki = pki();
    let limits = IngressLimits {
        handshake_timeout: Duration::from_secs(2),
        frame_timeout: Duration::from_millis(100),
        max_frame_bytes: 1_024,
    };
    let ingress = Arc::new(build_ingress(&pki, store_for(&pki), limits));

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client.write_all(&0u32.to_be_bytes()).await.unwrap();
    let _ = client.shutdown().await;
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameBounds
    );

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client.write_all(&1_025u32.to_be_bytes()).await.unwrap();
    let _ = client.shutdown().await;
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameBounds
    );

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client.write_all(&100u32.to_be_bytes()).await.unwrap();
    client.write_all(b"short").await.unwrap();
    let _ = client.shutdown().await;
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameIncomplete
    );

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    client.write_all(b"x").await.unwrap();
    let _ = client.shutdown().await;
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameTrailing
    );

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    let _ = client.shutdown().await;
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameTrailing
    );

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    drop(client);
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::FrameIncomplete
    );

    let (address, server) = spawn_server(ingress).await;
    let _client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::Timeout
    );
}

#[tokio::test]
async fn malformed_duplicate_and_ambiguous_identity_payloads_reject() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let hostile = [
        br#"{"ncp_version":"1.0","kind":"open_session","kind":"open_session"}"#.to_vec(),
        b"{not-json".to_vec(),
        {
            let mut value: Value =
                serde_json::from_slice(&payload(PRINCIPAL, ENTITY, "commander", "control"))
                    .unwrap();
            value["identity"]["unexpected"] = json!("laundered");
            serde_json::to_vec(&value).unwrap()
        },
    ];
    for bytes in hostile {
        let (address, server) = spawn_server(Arc::clone(&ingress)).await;
        let mut client = connect(address, client_config(&pki, Some(&pki.client)))
            .await
            .unwrap();
        write_frame(&mut client, &bytes).await.unwrap();
        assert!(matches!(
            server.await.unwrap().unwrap_err().code(),
            ErrorCode::PayloadInvalid | ErrorCode::IdentityMismatch
        ));
    }
}

#[tokio::test]
async fn rotation_uses_one_current_snapshot_without_global_invalidation() {
    let pki = pki();
    let manifests = store_for(&pki);
    let ingress = Arc::new(build_ingress(
        &pki,
        Arc::clone(&manifests),
        IngressLimits::default(),
    ));
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");

    let (address, server) = spawn_server(Arc::clone(&ingress)).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    client.get_ref().0.ready(Interest::WRITABLE).await.unwrap();

    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let mut value: Value =
        serde_json::from_slice(&manifest_bytes(2, &fingerprint, PRINCIPAL, ENTITY, ROUTE)).unwrap();
    value["principals"].as_array_mut().unwrap().push(json!({
        "principal_id": "unrelated-principal",
        "entity_id": "unrelated-entity",
        "role": "observer",
        "certificate_sha256":
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "grants": [{
            "route": "ncp/observation/read",
            "plane": "observation",
            "message_class": "observation_frame"
        }]
    }));
    let rotated = serde_json::to_vec(&value).unwrap();
    assert_eq!(
        manifests.rotate(&rotated, &sha256_hex(&rotated)).unwrap(),
        RotationOutcome::Applied
    );
    client.shutdown().await.unwrap();
    let message = server.await.unwrap().unwrap();
    assert_eq!(message.context().manifest_generation(), 2);

    let (address, server) = spawn_server(ingress).await;
    let mut client = connect(address, client_config(&pki, Some(&pki.client)))
        .await
        .unwrap();
    client
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .unwrap();
    client.write_all(&bytes).await.unwrap();
    let replacement = manifest_bytes(
        3,
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "replacement-principal",
        "replacement-entity",
        ROUTE,
    );
    manifests
        .rotate(&replacement, &sha256_hex(&replacement))
        .unwrap();
    client.shutdown().await.unwrap();
    assert_eq!(
        server.await.unwrap().unwrap_err().code(),
        ErrorCode::ManifestDenied
    );
}

#[test]
fn manifest_digest_generation_and_shape_are_fail_closed() {
    let pki = pki();
    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let bytes = manifest_bytes(2, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    let digest = sha256_hex(&bytes);
    let store = ManifestStore::new(&bytes, &digest).unwrap();

    assert_eq!(
        store.rotate(&bytes, &digest).unwrap(),
        RotationOutcome::Unchanged
    );
    let lower = manifest_bytes(1, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    assert_eq!(
        store
            .rotate(&lower, &sha256_hex(&lower))
            .unwrap_err()
            .code(),
        ErrorCode::ManifestRollback
    );
    let different_same_generation = manifest_bytes(2, &fingerprint, PRINCIPAL, ENTITY, "ncp/other");
    assert_eq!(
        store
            .rotate(
                &different_same_generation,
                &sha256_hex(&different_same_generation)
            )
            .unwrap_err()
            .code(),
        ErrorCode::ManifestEquivocation
    );
    assert_eq!(
        ManifestStore::new(&bytes, &"0".repeat(64))
            .unwrap_err()
            .code(),
        ErrorCode::ManifestDigest
    );

    let mut invalid: Value = serde_json::from_slice(&bytes).unwrap();
    invalid["default_deny"] = json!(false);
    let invalid = serde_json::to_vec(&invalid).unwrap();
    assert_eq!(
        ManifestStore::new(&invalid, &sha256_hex(&invalid))
            .unwrap_err()
            .code(),
        ErrorCode::ManifestInvalid
    );

    for mutation in [
        {
            let mut value: Value = serde_json::from_slice(&bytes).unwrap();
            value["extra"] = json!(true);
            serde_json::to_vec(&value).unwrap()
        },
        {
            let mut value: Value = serde_json::from_slice(&bytes).unwrap();
            value["principals"][0]["role"] = json!("unknown");
            serde_json::to_vec(&value).unwrap()
        },
        {
            let mut value: Value = serde_json::from_slice(&bytes).unwrap();
            value["principals"][0]["grants"][0]["route"] = json!("ncp/*");
            serde_json::to_vec(&value).unwrap()
        },
        {
            let mut value: Value = serde_json::from_slice(&bytes).unwrap();
            let duplicate = value["principals"][0].clone();
            value["principals"].as_array_mut().unwrap().push(duplicate);
            serde_json::to_vec(&value).unwrap()
        },
        {
            let mut value: Value = serde_json::from_slice(&bytes).unwrap();
            let duplicate = value["principals"][0]["grants"][0].clone();
            value["principals"][0]["grants"]
                .as_array_mut()
                .unwrap()
                .push(duplicate);
            serde_json::to_vec(&value).unwrap()
        },
    ] {
        assert_eq!(
            ManifestStore::new(&mutation, &sha256_hex(&mutation))
                .unwrap_err()
                .code(),
            ErrorCode::ManifestInvalid
        );
    }

    let duplicate_key = format!(
        r#"{{"schema":"{MANIFEST_SCHEMA}","generation":1,"generation":2,"default_deny":true,"principals":[]}}"#
    );
    assert_eq!(
        ManifestStore::new(
            duplicate_key.as_bytes(),
            &sha256_hex(duplicate_key.as_bytes())
        )
        .unwrap_err()
        .code(),
        ErrorCode::ManifestInvalid
    );

    let oversized = vec![b' '; ncp_tls_terminating_ingress_prototype::MAX_MANIFEST_BYTES + 1];
    assert_eq!(
        ManifestStore::new(&oversized, &sha256_hex(&oversized))
            .unwrap_err()
            .code(),
        ErrorCode::ManifestBounds
    );
}

#[test]
fn concurrent_publication_is_linearized_and_equivocation_is_deterministic() {
    let pki = pki();
    let fingerprint = sha256_hex(pki.client.certificate.der().as_ref());
    let initial = manifest_bytes(1, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    let store = Arc::new(ManifestStore::new(&initial, &sha256_hex(&initial)).unwrap());

    let candidate_a = manifest_bytes(2, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
    let candidate_b = manifest_bytes(2, &fingerprint, PRINCIPAL, ENTITY, "ncp/other");
    let barrier = Arc::new(Barrier::new(3));
    let mut writers = Vec::new();
    for candidate in [candidate_a.clone(), candidate_b.clone()] {
        let store = Arc::clone(&store);
        let barrier = Arc::clone(&barrier);
        writers.push(std::thread::spawn(move || {
            barrier.wait();
            store.rotate(&candidate, &sha256_hex(&candidate))
        }));
    }
    barrier.wait();
    let outcomes = writers
        .into_iter()
        .map(|writer| writer.join().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| matches!(outcome, Ok(RotationOutcome::Applied)))
            .count(),
        1
    );
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| {
                matches!(
                    outcome,
                    Err(error) if error.code() == ErrorCode::ManifestEquivocation
                )
            })
            .count(),
        1
    );
    let (generation, digest) = store.current_version().unwrap();
    assert_eq!(generation, 2);
    assert!(digest == sha256_hex(&candidate_a) || digest == sha256_hex(&candidate_b));

    let running = Arc::new(AtomicBool::new(true));
    let reader_store = Arc::clone(&store);
    let reader_running = Arc::clone(&running);
    let reader = std::thread::spawn(move || {
        while reader_running.load(Ordering::Acquire) {
            let (generation, digest) = reader_store.current_version().unwrap();
            assert!((2..=8).contains(&generation));
            assert_eq!(digest.len(), 64);
        }
    });
    let mut storm = Vec::new();
    for generation in 3..=8 {
        let store = Arc::clone(&store);
        let candidate = manifest_bytes(generation, &fingerprint, PRINCIPAL, ENTITY, ROUTE);
        storm.push(std::thread::spawn(move || {
            store.rotate(&candidate, &sha256_hex(&candidate))
        }));
    }
    for writer in storm {
        let result = writer.join().unwrap();
        assert!(
            matches!(result, Ok(RotationOutcome::Applied))
                || matches!(
                    result,
                    Err(error) if error.code() == ErrorCode::ManifestRollback
                )
        );
    }
    running.store(false, Ordering::Release);
    reader.join().unwrap();
    assert_eq!(store.current_version().unwrap().0, 8);
}

#[tokio::test]
async fn reconstructed_store_has_a_distinct_boot_epoch() {
    let pki = pki();
    let bytes = payload(PRINCIPAL, ENTITY, "commander", "control");
    let mut boot_ids = Vec::new();

    for _ in 0..2 {
        let ingress = Arc::new(build_ingress(
            &pki,
            store_for(&pki),
            IngressLimits::default(),
        ));
        let (address, server) = spawn_server(ingress).await;
        let mut client = connect(address, client_config(&pki, Some(&pki.client)))
            .await
            .unwrap();
        write_frame(&mut client, &bytes).await.unwrap();
        boot_ids.push(*server.await.unwrap().unwrap().context().boot_id());
    }
    assert_ne!(boot_ids[0], boot_ids[1]);
}

#[tokio::test]
async fn external_openssl_tls12_client_cannot_negotiate() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let (address, server) = spawn_server(ingress).await;

    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let directory =
        std::env::temp_dir().join(format!("ncp-tls12-negative-{}-{nonce}", std::process::id()));
    fs::create_dir(&directory).unwrap();
    let root_path = directory.join("root.pem");
    let cert_path = directory.join("client.pem");
    let key_path = directory.join("client-key.pem");
    fs::write(&root_path, pki.root.pem()).unwrap();
    fs::write(&cert_path, pki.client.certificate.pem()).unwrap();
    fs::write(&key_path, pki.client.key.serialize_pem()).unwrap();

    let connect_address = address.to_string();
    let output = tokio::task::spawn_blocking(move || {
        Command::new("openssl")
            .args([
                "s_client",
                "-connect",
                &connect_address,
                "-tls1_2",
                "-CAfile",
                root_path.to_str().unwrap(),
                "-cert",
                cert_path.to_str().unwrap(),
                "-key",
                key_path.to_str().unwrap(),
                "-alpn",
                std::str::from_utf8(ALPN_PROTOCOL).unwrap(),
                "-brief",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
    })
    .await
    .unwrap()
    .unwrap();
    let _ = fs::remove_dir_all(directory);

    assert!(
        !output.status.success(),
        "OpenSSL TLS 1.2 unexpectedly negotiated: {}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(server.await.unwrap().unwrap_err().code(), ErrorCode::Tls);
}

#[tokio::test]
async fn external_openssl_tls13_transcript_has_no_session_ticket() {
    let pki = pki();
    let ingress = Arc::new(build_ingress(
        &pki,
        store_for(&pki),
        IngressLimits::default(),
    ));
    let (address, server) = spawn_server(ingress).await;
    let message = payload(PRINCIPAL, ENTITY, "commander", "control");
    let mut framed = Vec::with_capacity(message.len() + 4);
    framed.extend_from_slice(&(message.len() as u32).to_be_bytes());
    framed.extend_from_slice(&message);

    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let directory = std::env::temp_dir().join(format!(
        "ncp-tls13-ticket-negative-{}-{nonce}",
        std::process::id()
    ));
    fs::create_dir(&directory).unwrap();
    let root_path = directory.join("root.pem");
    let cert_path = directory.join("client.pem");
    let key_path = directory.join("client-key.pem");
    fs::write(&root_path, pki.root.pem()).unwrap();
    fs::write(&cert_path, pki.client.certificate.pem()).unwrap();
    fs::write(&key_path, pki.client.key.serialize_pem()).unwrap();

    let connect_address = address.to_string();
    let output = tokio::task::spawn_blocking(move || {
        let mut child = Command::new("openssl")
            .args([
                "s_client",
                "-connect",
                &connect_address,
                "-tls1_3",
                "-CAfile",
                root_path.to_str().unwrap(),
                "-cert",
                cert_path.to_str().unwrap(),
                "-key",
                key_path.to_str().unwrap(),
                "-alpn",
                std::str::from_utf8(ALPN_PROTOCOL).unwrap(),
                "-msg",
                "-no_ign_eof",
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(&framed).unwrap();
        child.wait_with_output()
    })
    .await
    .unwrap()
    .unwrap();
    let _ = fs::remove_dir_all(directory);

    assert!(
        output.status.success(),
        "OpenSSL TLS 1.3 positive failed: {}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let transcript = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        !transcript.contains("NewSessionTicket"),
        "server emitted a TLS 1.3 session ticket"
    );
    let accepted = server.await.unwrap().unwrap();
    assert_eq!(accepted.payload(), message);
}
