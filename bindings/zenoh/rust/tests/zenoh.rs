//! Tests of the Zenoh binding (specification, section 9.2), with two Zenoh sessions in one process.
//! The TLS tests need the `openssl` command; they are skipped without it.
use ncp::{
    frame, Array, Channel, Client, Contract, Decoded, Delivery, Error, Handler, Owner, Reply,
};
use ncp_zenoh::{exchange_key, ServeOptions, Server, StreamSender, TlsFiles, ZenohChannel};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};
use zenoh::{Config, Session, Wait};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}"#;
const TIMEOUT: Duration = Duration::from_millis(500);

type Counts = Arc<Mutex<HashMap<i64, u32>>>;

/// `echo` returns the request body and arrays, `fail` fails; every body member `k` is counted.
struct Counting {
    counts: Counts,
}

impl Handler for Counting {
    fn validate(&mut self, _op: &str, _request: &Decoded) -> Result<(), String> {
        Ok(())
    }
    fn execute(
        &mut self,
        op: &str,
        request: &Decoded,
    ) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        if let Some(k) = request.message["body"]["k"].as_i64() {
            *self.counts.lock().unwrap().entry(k).or_default() += 1;
        }
        if op == "fail" {
            return Err("requested failure".into());
        }
        if op == "sleep" {
            let seconds = request.message["body"]["seconds"].as_f64().unwrap_or(0.0);
            std::thread::sleep(Duration::from_secs_f64(seconds));
        }
        Ok(Reply {
            body: request.message["body"].clone(),
            arrays: request.owned_arrays(),
        })
    }
}

fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

fn plain(listen: &[&str], connect: &[&str]) -> Config {
    let mut config = Config::default();
    config.insert_json5("mode", r#""peer""#).unwrap();
    config
        .insert_json5("scouting/multicast/enabled", "false")
        .unwrap();
    config
        .insert_json5("listen/endpoints", &json!(listen).to_string())
        .unwrap();
    config
        .insert_json5("connect/endpoints", &json!(connect).to_string())
        .unwrap();
    config
}

fn wait_for_peer(session: &Session, limit: Duration) -> bool {
    let deadline = Instant::now() + limit;
    while Instant::now() < deadline {
        if session.info().peers_zid().wait().next().is_some() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    false
}

/// An owner session serving `ncp/x/<name>` in a thread, and a client session.
struct Service {
    owner: Session,
    client: Session,
    name: String,
    counts: Counts,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    linked: bool,
}

impl Service {
    fn start(
        name: String,
        owner_config: Config,
        client_config: Config,
        options: ServeOptions,
    ) -> Service {
        let owner = zenoh::open(owner_config).wait().unwrap();
        let client = zenoh::open(client_config).wait().unwrap();
        let counts = Counts::default();
        let stop = Arc::new(AtomicBool::new(false));
        let (ready, declared) = mpsc::channel();
        let thread = {
            let (owner, name, counts, stop) =
                (owner.clone(), name.clone(), counts.clone(), stop.clone());
            std::thread::spawn(move || {
                let contract = Contract::from_bytes(CONTRACT.to_vec()).unwrap();
                let make_owner = || {
                    Owner::new(
                        &contract.application,
                        &contract.identity,
                        Counting {
                            counts: counts.clone(),
                        },
                        contract.operations.clone(),
                        ncp::MAX_BOUND,
                    )
                };
                let mut server = Server::declare(&owner, &name, make_owner, options).unwrap();
                ready.send(()).unwrap();
                server.run(&stop).unwrap();
            })
        };
        declared.recv_timeout(Duration::from_secs(5)).unwrap();
        let linked = wait_for_peer(&client, Duration::from_secs(3));
        Service {
            owner,
            client,
            name,
            counts,
            stop,
            thread: Some(thread),
            linked,
        }
    }

    fn plain(options: ServeOptions) -> Service {
        let endpoint = format!("tcp/127.0.0.1:{}", free_port());
        let service = Service::start(
            new_name(),
            plain(&[&endpoint], &[]),
            plain(&[], &[&endpoint]),
            options,
        );
        assert!(
            service.linked && service.answers(),
            "the service never answered"
        );
        service
    }

    /// Wait until the service answers a request of an unknown session. A linked peer does not
    /// yet mean that the declaration of the service has reached the client; without this wait,
    /// a test that expects no reply could pass without reaching the owner.
    fn answers(&self) -> bool {
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            let probe = json!({"ncp": 2, "session": ncp::random_session(), "seq": 1, "op": "echo",
                               "ack": "0".repeat(64), "body": {}});
            let frame_bytes = frame::encode(&probe, &[]).unwrap();
            if !self
                .raw_within(frame_bytes, Duration::from_millis(300))
                .is_empty()
            {
                return true;
            }
        }
        false
    }

    fn channel(&self) -> ZenohChannel {
        ZenohChannel::new(&self.client, &self.name)
            .unwrap()
            .with_timeout(TIMEOUT)
    }

    fn client<C: Channel>(&self, channel: C) -> Client<C> {
        let contract = Contract::from_bytes(CONTRACT.to_vec()).unwrap();
        Client::new(channel, &contract.application, &contract.identity)
    }

    /// Send one frame as a query and return every reply frame.
    fn raw(&self, frame: Vec<u8>) -> Vec<Vec<u8>> {
        self.raw_within(frame, Duration::from_secs(1))
    }

    fn raw_within(&self, frame: Vec<u8>, limit: Duration) -> Vec<Vec<u8>> {
        let replies = self
            .client
            .get(exchange_key(&self.name).unwrap())
            .payload(frame)
            .timeout(limit)
            .wait()
            .unwrap();
        let mut frames = Vec::new();
        while let Ok(reply) = replies.recv() {
            if let Ok(sample) = reply.result() {
                frames.push(sample.payload().to_bytes().into_owned());
            }
        }
        frames
    }

    fn counts(&self) -> HashMap<i64, u32> {
        self.counts.lock().unwrap().clone()
    }
}

impl Drop for Service {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
        let _ = self.client.close().wait();
        let _ = self.owner.close().wait();
    }
}

fn new_name() -> String {
    format!("test/{}", &ncp::random_session()[..8])
}

fn counts(pairs: &[(i64, u32)]) -> HashMap<i64, u32> {
    pairs.iter().copied().collect()
}

#[test]
fn a_session_runs_and_its_transcript_verifies() {
    let service = Service::plain(ServeOptions::default());
    assert!(service.linked);
    let path = std::env::temp_dir().join(format!("ncp-zenoh-{}.ncpt", ncp::random_session()));
    let tap = ncp::Tap::create(&path).unwrap();
    let mut client = service.client(service.channel().with_tap(tap));
    let info = client.open().unwrap();
    assert_eq!(info["application"], "echo");
    let one = client.call("echo", json!({"k": 1, "x": "y"}), &[]).unwrap();
    assert_eq!(one.message["body"], json!({"k": 1, "x": "y"}));
    let values = Array::from_u32(&[1, 2, 3]);
    let two = client
        .call("echo", json!({"k": 2, "a": values.reference(0)}), &[values])
        .unwrap();
    assert_eq!(two.array_u32(0).unwrap(), vec![1, 2, 3]);
    client.close().unwrap();
    let reports = ncp::transcript::verify(&path).unwrap();
    let report = reports.values().next().unwrap();
    assert!(report.complete, "{report:?}");
    assert!(report.problems.is_empty(), "{report:?}");
    assert_eq!(service.counts(), counts(&[(1, 1), (2, 1)]));
    std::fs::remove_file(path).unwrap();
}

/// A channel that loses the first query or the first reply of one request, as a network can.
struct Dropping {
    inner: ZenohChannel,
    lose_query: bool,
    seq: u64,
    lost: Arc<AtomicBool>,
}

fn seq_of(frame_bytes: &[u8]) -> u64 {
    frame::decode(frame_bytes.to_vec(), ncp::MAX_BOUND)
        .unwrap()
        .message["seq"]
        .as_u64()
        .unwrap()
}

impl Channel for Dropping {
    fn lossy(&self) -> bool {
        true
    }
    fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
        if self.lose_query
            && seq_of(frame_bytes) == self.seq
            && !self.lost.swap(true, Ordering::AcqRel)
        {
            return Ok(());
        }
        self.inner.send(frame_bytes)
    }
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, Error> {
        let frame_bytes = self.inner.receive(bound)?;
        if !self.lose_query
            && seq_of(&frame_bytes) == self.seq
            && !self.lost.swap(true, Ordering::AcqRel)
        {
            return Err(Error::Io(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                "lost",
            )));
        }
        Ok(frame_bytes)
    }
}

#[test]
fn a_lost_reply_or_query_still_runs_each_step_once() {
    for lose_query in [false, true] {
        let service = Service::plain(ServeOptions::default());
        let lost = Arc::new(AtomicBool::new(false));
        let channel = Dropping {
            inner: service.channel(),
            lose_query,
            seq: 2,
            lost: lost.clone(),
        };
        let mut client = service.client(channel);
        client.open().unwrap();
        for k in 1..=3 {
            let reply = client.call("echo", json!({"k": k}), &[]).unwrap();
            assert_eq!(reply.message["body"], json!({"k": k}));
        }
        client.close().unwrap();
        assert!(lost.load(Ordering::Acquire), "lose_query: {lose_query}");
        assert_eq!(
            service.counts(),
            counts(&[(1, 1), (2, 1), (3, 1)]),
            "lose_query: {lose_query}"
        );
    }
}

#[test]
fn a_bad_frame_gets_no_reply_and_a_session_the_owner_does_not_hold_is_possibly_executed() {
    let service = Service::plain(ServeOptions::default());
    let request = |session: &str, seq: u64| {
        let ack = if seq == 0 {
            json!(null)
        } else {
            json!("0".repeat(64))
        };
        let message = json!({"ncp": 2, "session": session, "seq": seq, "op": "echo",
                             "ack": ack, "body": {"k": 9}});
        frame::encode(&message, &[]).unwrap()
    };
    let mut bad = request(&ncp::random_session(), 1);
    bad[20] ^= 0x01;
    assert!(service.raw(bad).is_empty());
    // seq > 0: the owner may have forgotten the session or restarted (rule 9.2.7).
    for (seq, expected) in [
        (1, ("ended", "session_expired")),
        (0, ("rejected", "not_open")),
    ] {
        let replies = service.raw(request(&ncp::random_session(), seq));
        assert_eq!(replies.len(), 1, "seq {seq}");
        let message = frame::decode(replies[0].clone(), ncp::MAX_BOUND)
            .unwrap()
            .message;
        assert_eq!(
            (message["outcome"].clone(), message["code"].clone()),
            (json!(expected.0), json!(expected.1)),
            "seq {seq}"
        );
    }
    assert!(service.counts().is_empty());
}

#[test]
fn above_the_limit_an_open_is_refused() {
    let options = ServeOptions {
        max_sessions: 1,
        ..ServeOptions::default()
    };
    let service = Service::plain(options);
    let mut first = service.client(service.channel());
    first.open().unwrap();
    let mut second = service.client(service.channel());
    match second.open() {
        Err(Error::Rejected { code, .. }) => assert_eq!(code, "refused"),
        other => panic!("unexpected: {other:?}"),
    }
    first.close().unwrap();
}

#[test]
fn sessions_are_independent_and_a_failure_ends_only_its_own() {
    let service = Service::plain(ServeOptions::default());
    let (mut first, mut second) = (
        service.client(service.channel()),
        service.client(service.channel()),
    );
    first.open().unwrap();
    second.open().unwrap();
    first.call("echo", json!({"k": 1}), &[]).unwrap();
    match second.call("fail", json!({"k": 2}), &[]) {
        Err(Error::Ended { code, executed }) => {
            assert_eq!((code.as_str(), executed), ("owner_failure", "unknown"))
        }
        other => panic!("unexpected: {other:?}"),
    }
    first.call("echo", json!({"k": 3}), &[]).unwrap();
    first.close().unwrap();
    assert_eq!(service.counts(), counts(&[(1, 1), (2, 1), (3, 1)]));
}

#[test]
fn a_forgotten_session_ends_with_session_expired() {
    let options = ServeOptions {
        expire_after: Duration::from_millis(300),
        ..ServeOptions::default()
    };
    let service = Service::plain(options);
    let mut client = service.client(service.channel());
    client.open().unwrap();
    client.call("echo", json!({"k": 1}), &[]).unwrap();
    std::thread::sleep(Duration::from_millis(600));
    match client.call("echo", json!({"k": 2}), &[]) {
        Err(Error::Ended { code, executed }) => {
            assert_eq!((code.as_str(), executed), ("session_expired", "unknown"))
        }
        other => panic!("unexpected: {other:?}"),
    }
    assert_eq!(service.counts(), counts(&[(1, 1)]));
}

#[test]
fn a_step_longer_than_the_expiry_time_keeps_its_session() {
    let options = ServeOptions {
        expire_after: Duration::from_millis(400),
        ..ServeOptions::default()
    };
    let service = Service::plain(options);
    let channel = ZenohChannel::new(&service.client, &service.name)
        .unwrap()
        .with_timeout(Duration::from_secs(2));
    let mut client = service.client(channel);
    client.open().unwrap();
    client
        .call("sleep", json!({"k": 1, "seconds": 0.8}), &[])
        .unwrap();
    client.call("echo", json!({"k": 2}), &[]).unwrap(); // the session is still known
    client.close().unwrap();
    assert_eq!(service.counts(), counts(&[(1, 1), (2, 1)]));
}

#[test]
fn a_subscriber_accepts_every_message_in_order() {
    let endpoint = format!("tcp/127.0.0.1:{}", free_port());
    let publishing = zenoh::open(plain(&[&endpoint], &[])).wait().unwrap();
    let subscribing = zenoh::open(plain(&[], &[&endpoint])).wait().unwrap();
    assert!(wait_for_peer(&subscribing, Duration::from_secs(3)));
    let contract = "a".repeat(64);
    let checker = Arc::new(Mutex::new(ncp::Subscriber::new([contract.clone()])));
    let (deliver, delivered) = mpsc::channel();
    let deliver = Mutex::new(deliver);
    let _subscriber = ncp_zenoh::subscribe(&subscribing, "test/sensors", move |frame_bytes| {
        let (delivery, decoded) = checker.lock().unwrap().receive(frame_bytes);
        let t = decoded
            .map(|d| d.message["body"]["t"].clone())
            .unwrap_or(Value::Null);
        deliver.lock().unwrap().send((delivery, t)).unwrap();
    })
    .unwrap();
    std::thread::sleep(Duration::from_millis(300)); // let the subscription reach the publisher
    let sender = StreamSender::declare(&publishing, "test/sensors").unwrap();
    let mut publisher = ncp::Publisher::new("sensors", &contract).unwrap();
    for t in 0..20 {
        sender
            .send(&publisher.publish(json!({"t": t}), &[]).unwrap())
            .unwrap();
    }
    for t in 0..20 {
        let (delivery, value) = delivered.recv_timeout(Duration::from_secs(5)).unwrap();
        assert!(
            matches!(delivery, Delivery::Accepted { lost: 0 }),
            "{delivery:?}"
        );
        assert_eq!(value, json!(t));
    }
    subscribing.close().wait().unwrap();
    publishing.close().wait().unwrap();
}

#[test]
fn names_must_be_plain_keys() {
    for name in ["", "a/*", "a//b", "a/$b", "a b", &"x".repeat(300)] {
        assert!(exchange_key(name).is_err(), "{name:?}");
    }
    assert_eq!(exchange_key("lab/nest-1").unwrap(), "ncp/x/lab/nest-1");
}

// ------------------------------------------------------------------------------- TLS (rule 9.2.6)

fn openssl(directory: &Path, args: &[&str]) {
    let status = Command::new("openssl")
        .args(args)
        .current_dir(directory)
        .output()
        .unwrap();
    assert!(
        status.status.success(),
        "openssl {args:?}: {}",
        String::from_utf8_lossy(&status.stderr)
    );
}

fn make_ca(directory: &Path, name: &str) {
    openssl(
        directory,
        &[
            "genpkey",
            "-algorithm",
            "EC",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-out",
            &format!("{name}.key"),
        ],
    );
    std::fs::write(
        directory.join(format!("{name}.ext")),
        "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n",
    )
    .unwrap();
    openssl(
        directory,
        &[
            "req",
            "-new",
            "-key",
            &format!("{name}.key"),
            "-subj",
            &format!("/CN={name}"),
            "-out",
            &format!("{name}.csr"),
        ],
    );
    openssl(
        directory,
        &[
            "x509",
            "-req",
            "-in",
            &format!("{name}.csr"),
            "-signkey",
            &format!("{name}.key"),
            "-days",
            "30",
            "-extfile",
            &format!("{name}.ext"),
            "-out",
            &format!("{name}.pem"),
        ],
    );
}

fn make_certificate(directory: &Path, ca: &str, name: &str) {
    openssl(
        directory,
        &[
            "genpkey",
            "-algorithm",
            "EC",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-out",
            &format!("{name}.key"),
        ],
    );
    std::fs::write(
        directory.join(format!("{name}.ext")),
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n\
         extendedKeyUsage=serverAuth,clientAuth\nsubjectAltName=DNS:localhost\n",
    )
    .unwrap();
    openssl(
        directory,
        &[
            "req",
            "-new",
            "-key",
            &format!("{name}.key"),
            "-subj",
            &format!("/CN={name}"),
            "-out",
            &format!("{name}.csr"),
        ],
    );
    openssl(
        directory,
        &[
            "x509",
            "-req",
            "-in",
            &format!("{name}.csr"),
            "-CA",
            &format!("{ca}.pem"),
            "-CAkey",
            &format!("{ca}.key"),
            "-CAcreateserial",
            "-days",
            "30",
            "-extfile",
            &format!("{name}.ext"),
            "-out",
            &format!("{name}.pem"),
        ],
    );
}

fn files(directory: &Path, ca: &str, name: &str) -> TlsFiles {
    let path = |file: String| directory.join(file).display().to_string();
    TlsFiles {
        root_ca_certificate: path(format!("{ca}.pem")),
        certificate: path(format!("{name}.pem")),
        private_key: path(format!("{name}.key")),
    }
}

/// Allow only the peer whose certificate names `allowed` to query `service`.
fn access_control(config: &mut Config, service: &str, allowed: &str) {
    let rules = json!({
        "enabled": true,
        "default_permission": "deny",
        "rules": [{"id": "ncp-exchange", "messages": ["query", "reply", "declare_queryable"],
                   "flows": ["ingress", "egress"], "permission": "allow",
                   "key_exprs": [exchange_key(service).unwrap()]}],
        "subjects": [{"id": "allowed-client", "cert_common_names": [allowed]}],
        "policies": [{"rules": ["ncp-exchange"], "subjects": ["allowed-client"]}],
    });
    config
        .insert_json5("access_control", &rules.to_string())
        .unwrap();
}

struct Certificates {
    directory: PathBuf,
}

impl Certificates {
    fn make() -> Option<Certificates> {
        if Command::new("openssl").arg("version").output().is_err() {
            return None; // no openssl: the TLS tests do not run
        }
        let directory =
            std::env::temp_dir().join(format!("ncp-zenoh-tls-{}", ncp::random_session()));
        std::fs::create_dir_all(&directory).unwrap();
        make_ca(&directory, "ca");
        make_ca(&directory, "other-ca");
        for name in ["owner", "client-a", "client-b"] {
            make_certificate(&directory, "ca", name);
        }
        make_certificate(&directory, "other-ca", "intruder");
        Some(Certificates { directory })
    }

    fn service(&self, client: &str, ca: &str, allowed: Option<&str>) -> Service {
        let endpoint = format!("tls/localhost:{}", free_port());
        let name = new_name();
        let owner_files = files(&self.directory, "ca", "owner");
        let mut owner_config = ncp_zenoh::secure_config(&owner_files, &[&endpoint], &[]).unwrap();
        if let Some(allowed) = allowed {
            access_control(&mut owner_config, &name, allowed);
        }
        let client_files = files(&self.directory, ca, client);
        let client_config = ncp_zenoh::secure_config(&client_files, &[], &[&endpoint]).unwrap();
        Service::start(name, owner_config, client_config, ServeOptions::default())
    }
}

impl Drop for Certificates {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.directory);
    }
}

fn admitted(service: &Service) -> bool {
    let mut client = service.client(service.channel());
    match client.open() {
        Ok(_) => {
            assert_eq!(
                client.call("echo", json!({"k": 1}), &[]).unwrap().message["body"],
                json!({"k": 1})
            );
            client.close().unwrap();
            true
        }
        Err(Error::Ended { code, .. }) if code == "timeout" => {
            assert!(service.counts().is_empty());
            false
        }
        Err(other) => panic!("unexpected: {other:?}"),
    }
}

#[test]
fn mutual_tls_and_access_control() {
    let Some(certificates) = Certificates::make() else {
        eprintln!("skipped: no openssl");
        return;
    };
    let service = certificates.service("client-a", "ca", None);
    assert!(
        service.linked && admitted(&service),
        "a client with a certificate of the CA"
    );
    drop(service);
    let service = certificates.service("intruder", "other-ca", None);
    assert!(
        !service.linked && !admitted(&service),
        "a client of another CA"
    );
    drop(service);
    for (client, allowed, expected) in [
        ("client-a", "client-a", true),
        ("client-b", "client-a", false),
    ] {
        let service = certificates.service(client, "ca", Some(allowed));
        assert!(
            service.linked,
            "{client}: both certificates come from the CA"
        );
        assert_eq!(
            admitted(&service),
            expected,
            "{client} with access control for {allowed}"
        );
    }
    let service = certificates.service("client-b", "ca", None);
    assert!(
        admitted(&service),
        "control: without access control, client-b is admitted"
    );
}

/// The Rust client against the Python owner (bindings/zenoh/python/tests/zenoh_echo_owner.py).
/// Runs when NCP_ZENOH_PYTHON names a Python with eclipse-zenoh.
#[test]
fn rust_client_with_the_python_owner() {
    let Some(python) = std::env::var_os("NCP_ZENOH_PYTHON") else {
        eprintln!("skipped: NCP_ZENOH_PYTHON is not set");
        return;
    };
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../python/tests/zenoh_echo_owner.py");
    let endpoint = format!("tcp/127.0.0.1:{}", free_port());
    let name = new_name();
    let log = std::env::temp_dir().join(format!("ncp-zenoh-log-{}.jsonl", ncp::random_session()));
    let mut owner = Command::new(python)
        .args([
            "-I".as_ref(),
            script.as_os_str(),
            name.as_ref(),
            endpoint.as_ref(),
        ])
        .env("NCP_EXECUTION_LOG", &log)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    let mut line = String::new();
    std::io::BufRead::read_line(
        &mut std::io::BufReader::new(owner.stdout.take().unwrap()),
        &mut line,
    )
    .unwrap();
    assert_eq!(line.trim(), "ready");
    let session = zenoh::open(plain(&[], &[&endpoint])).wait().unwrap();
    assert!(wait_for_peer(&session, Duration::from_secs(5)));
    let lost = Arc::new(AtomicBool::new(false));
    let channel = Dropping {
        inner: ZenohChannel::new(&session, &name)
            .unwrap()
            .with_timeout(TIMEOUT),
        lose_query: false,
        seq: 2,
        lost: lost.clone(),
    };
    let contract = Contract::from_bytes(CONTRACT.to_vec()).unwrap();
    let mut client = Client::new(channel, &contract.application, &contract.identity);
    client.open().unwrap();
    for k in 1..=3 {
        let values = Array::from_u32(&[1, 2, 3]);
        let reply = client
            .call("echo", json!({"k": k, "a": values.reference(0)}), &[values])
            .unwrap();
        assert_eq!(reply.message["body"]["k"], json!(k));
        assert_eq!(reply.array_u32(0).unwrap(), vec![1, 2, 3]);
    }
    client.close().unwrap();
    assert!(lost.load(Ordering::Acquire));
    drop(owner.stdin.take()); // the owner stops when its input closes
    owner.wait().unwrap();
    let executed: Vec<i64> = std::fs::read_to_string(&log)
        .unwrap()
        .lines()
        .map(|line| {
            serde_json::from_str::<Value>(line).unwrap()["k"]
                .as_i64()
                .unwrap()
        })
        .collect();
    assert_eq!(
        executed,
        vec![1, 2, 3],
        "the lost reply did not run step 2 again"
    );
    session.close().wait().unwrap();
    std::fs::remove_file(log).unwrap();
}
