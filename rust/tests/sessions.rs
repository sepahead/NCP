//! Sessions end to end: in-memory and lossy channels, TCP, Unix domain sockets, child processes,
//! servers, transcripts, streams, profiles, and the Python reference owner when `python3` is
//! available.

use ncp::frame::{self, Array, Key, HANDSHAKE_BOUND, MAX_BOUND};
use ncp::{
    declined, events, transcript, AppError, Channel, ChannelError, Client, Contract, Delivery,
    Error, Executed, Handler, Invalid, Limits, Lockstep, LockstepClient, OpenInfo, Owner,
    Publisher, Refused, Reply, Request, Stepper, Subscriber,
};
use serde_json::{json, Map, Value};
use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"big":{}},"streams":{"sensor":{}}}"#;

fn contract() -> Contract {
    Contract::from_bytes(CONTRACT.to_vec()).expect("contract")
}

#[derive(Clone, Default)]
struct Echo {
    executed: Arc<AtomicUsize>,
}

impl Handler for Echo {
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if request.body["invalid"] == true {
            return Err(declined("invalid requested"));
        }
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        self.executed.fetch_add(1, Ordering::SeqCst);
        match request.op {
            "fail" => Err("requested failure".into()),
            "big" => {
                let size = request.body["size"].as_u64().unwrap_or(0) as usize;
                if request.body["json"] == true {
                    Ok(json!({"blob": "z".repeat(size)}).into())
                } else {
                    let array = Array::from_u8(&vec![0; size]);
                    Ok(Reply {
                        body: json!({"blob": array.reference(0)}),
                        arrays: vec![array],
                    })
                }
            }
            _ => Ok(Reply {
                body: request.body.clone(),
                arrays: request.owned_arrays(),
            }),
        }
    }
}

fn quiet() -> Arc<dyn ncp::Observer> {
    Arc::new(events::Silent)
}

fn owner(handler: Echo, max_bound: usize) -> Owner<Echo> {
    Owner::new(contract(), handler)
        .with_max_bound(max_bound)
        .with_observer(quiet())
}

/// A channel that hands frames straight to an owner. `drop_responses` loses the next responses
/// after the owner handled the request, as a lossy binding can.
struct Memory<H: Handler> {
    owner: Owner<H>,
    inbox: VecDeque<Vec<u8>>,
    drop_responses: usize,
    lossy: bool,
}

impl<H: Handler> Channel for Memory<H> {
    fn lossy(&self) -> bool {
        self.lossy
    }
    fn local(&self) -> bool {
        true
    }
    fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
        let response = self
            .owner
            .handle(frame_bytes.to_vec())
            .map_err(std::io::Error::other)?;
        if self.drop_responses > 0 {
            self.drop_responses -= 1;
        } else {
            self.inbox.push_back(response.to_vec());
        }
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn memory_of<H: Handler>(owner: Owner<H>, lossy: bool, drop_responses: usize) -> Client<Memory<H>> {
    Client::new(
        Memory {
            owner,
            inbox: VecDeque::new(),
            drop_responses,
            lossy,
        },
        &contract(),
    )
    .with_observer(quiet())
}

fn memory(handler: Echo, lossy: bool, drop_responses: usize) -> Client<Memory<Echo>> {
    memory_of(owner(handler, MAX_BOUND), lossy, drop_responses)
}

fn all_dtypes() -> Vec<Array> {
    vec![
        Array::from_u8(&[0, 1, 255]),
        Array::from_i8(&[-128, 0, 127]),
        Array::from_u16(&[0, 65535]),
        Array::from_i16(&[-32768, 32767]),
        Array::from_u32(&[0, u32::MAX]),
        Array::from_i32(&[i32::MIN, i32::MAX]),
        Array::from_u64(&[0, u64::MAX]),
        Array::from_i64(&[i64::MIN, i64::MAX]),
        Array::from_f32(&[f32::MIN_POSITIVE, -0.0, f32::MAX]),
        Array::from_f64(&[f64::MIN_POSITIVE, -0.0, f64::MAX, std::f64::consts::PI]),
        Array::from_f64(&[]),
    ]
}

fn array_body(arrays: &[Array]) -> Value {
    Value::Array(
        arrays
            .iter()
            .enumerate()
            .map(|(i, a)| a.reference(i))
            .collect(),
    )
}

fn ended(result: Result<impl std::fmt::Debug, Error>) -> (String, Executed) {
    match result {
        Err(Error::Ended { code, executed, .. }) => (code, executed),
        other => panic!("expected an ended session, got {other:?}"),
    }
}

#[test]
fn ok_and_declined_advance_the_session() {
    let mut client = memory(Echo::default(), false, 0);
    let opened = client.open().expect("open");
    assert_eq!(opened["bound"], ncp::DEFAULT_BOUND);
    assert_eq!(client.nonce().map(str::len), Some(32));
    assert_eq!(
        client
            .call("echo", json!({"x": 1}), &[])
            .expect("call")
            .message["seq"],
        1
    );
    match client.call("echo", json!({"invalid": true}), &[]) {
        Err(Error::Declined { code, detail, .. }) => {
            assert_eq!(
                (code.as_str(), detail.as_str()),
                ("body_invalid", "invalid requested")
            )
        }
        other => panic!("expected declined, got {other:?}"),
    }
    assert_eq!(client.state().seq, 2);
    match client.call("missing", json!({}), &[]) {
        Err(Error::Declined { code, .. }) => assert_eq!(code, "unknown_op"),
        other => panic!("expected unknown_op, got {other:?}"),
    }
    assert_eq!(client.ping().expect("ping").message["body"], json!({}));
    assert_eq!(
        client
            .call("echo", json!({"x": 2}), &[])
            .expect("call")
            .message["seq"],
        5
    );
    client.close().expect("close");
    assert!(client.ended());
    assert!(matches!(
        client.call("echo", json!({}), &[]),
        Err(Error::Usage(_))
    ));
}

#[test]
fn arrays_of_every_dtype_round_trip() {
    let mut client = memory(Echo::default(), false, 0);
    client.open().expect("open");
    let arrays = all_dtypes();
    let reply = client
        .call("echo", json!({"v": array_body(&arrays)}), &arrays)
        .expect("call");
    for (index, array) in arrays.iter().enumerate() {
        assert_eq!(
            reply.array_bytes(index).expect("bytes"),
            &array.data[..],
            "array {index}"
        );
    }
    assert_eq!(reply.array_f64(9).expect("f64")[3], std::f64::consts::PI);
}

#[test]
fn endings_report_whether_the_request_executed() {
    let mut client = memory(Echo::default(), false, 0);
    client.open().expect("open");
    assert_eq!(
        ended(client.call("fail", json!({}), &[])),
        ("owner_failure".into(), Executed::Unknown)
    );
    let mut client =
        memory_of(owner(Echo::default(), HANDSHAKE_BOUND), false, 0).with_bound(HANDSHAKE_BOUND);
    client.open().expect("open");
    let (code, executed) = ended(client.call("big", json!({"size": HANDSHAKE_BOUND}), &[]));
    assert_eq!(
        (code.as_str(), executed),
        ("result_too_large", Executed::Yes)
    );
    let mut client = memory(Echo::default(), false, 0).with_bound(MAX_BOUND);
    client.open().expect("open");
    match client.call("big", json!({"size": frame::MAX_JSON, "json": true}), &[]) {
        Err(Error::Ended {
            code,
            executed,
            body,
            ..
        }) => {
            assert_eq!(
                (code.as_str(), executed),
                ("result_too_large", Executed::Yes)
            );
            assert_eq!(body["limit"], frame::MAX_JSON);
        }
        other => panic!("expected result_too_large, got {other:?}"),
    }
}

#[test]
fn a_lost_response_is_sent_again_and_executes_once() {
    let echo = Echo::default();
    let executed = echo.executed.clone();
    let mut client = memory(echo, true, 0);
    client.open().expect("open");
    client.channel_mut().drop_responses = 2;
    let reply = client.call("echo", json!({"n": 1}), &[]).expect("call");
    assert_eq!(reply.message["body"], json!({"n": 1}));
    assert_eq!(
        executed.load(Ordering::SeqCst),
        1,
        "a copy must not execute again"
    );
    client.channel_mut().drop_responses = 10;
    let (code, verdict) = ended(client.call("echo", json!({"n": 2}), &[]));
    assert_eq!(
        (code.as_str(), verdict),
        ("local.timeout", Executed::Unknown)
    );
}

#[test]
fn a_declined_answer_never_changes() {
    // Decision D1: the owner keeps the declined response, so a copy that arrives after the
    // application would accept the body still gets it, and nothing executes.
    struct Flaky {
        accept: Arc<AtomicUsize>,
        executed: Arc<AtomicUsize>,
    }
    impl Handler for Flaky {
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            if self.accept.load(Ordering::SeqCst) == 0 {
                return Err(declined("not yet"));
            }
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            self.executed.fetch_add(1, Ordering::SeqCst);
            Ok(json!({}).into())
        }
    }
    let (accept, executed) = (Arc::new(AtomicUsize::new(0)), Arc::new(AtomicUsize::new(0)));
    let mut owner = Owner::new(
        contract(),
        Flaky {
            accept: accept.clone(),
            executed: executed.clone(),
        },
    );
    let session = ncp::random_session();
    let open = json!({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": null,
                      "body": {"application": "echo", "contract": contract().identity, "bound": 65536}});
    let opened = owner
        .handle(frame::encode(&open, &[]).expect("open"))
        .expect("open");
    let step = json!({"ncp": 2, "session": session, "seq": 1, "op": "echo", "ack": frame::identity(&opened), "body": {}});
    let step = frame::encode(&step, &[]).expect("step");
    let first = owner.handle(step.clone()).expect("step");
    accept.store(1, Ordering::SeqCst);
    assert_eq!(owner.handle(step).expect("copy"), first);
    assert_eq!(executed.load(Ordering::SeqCst), 0);
}

#[test]
fn each_opening_has_its_own_nonce() {
    let session = ncp::random_session();
    let open = json!({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": null,
                      "body": {"application": "echo", "contract": contract().identity, "bound": 65536}});
    let open = frame::encode(&open, &[]).expect("open");
    let (mut first, mut second) = (
        owner(Echo::default(), MAX_BOUND),
        owner(Echo::default(), MAX_BOUND),
    );
    let a = first.handle(open.clone()).expect("open");
    let b = second.handle(open).expect("open");
    assert_ne!(a, b);
    let step = json!({"ncp": 2, "session": session, "seq": 1, "op": "echo", "ack": frame::identity(&a), "body": {}});
    let step = frame::encode(&step, &[]).expect("step");
    assert_eq!(
        frame::decode(
            first.handle(step.clone()).expect("step").to_vec(),
            MAX_BOUND
        )
        .expect("ok")
        .message["outcome"],
        "ok"
    );
    let replay =
        frame::decode(second.handle(step).expect("step").to_vec(), MAX_BOUND).expect("response");
    assert_eq!(replay.message["code"], "ack_mismatch");
}

#[test]
fn a_stopping_owner_admits_nothing_new() {
    let mut client = memory(Echo::default(), false, 0);
    client.open().expect("open");
    client.call("echo", json!({}), &[]).expect("call");
    client.channel_mut().owner.stop();
    let (code, verdict) = ended(client.call("echo", json!({}), &[]));
    assert_eq!((code.as_str(), verdict), ("shutdown", Executed::No));
}

#[test]
fn several_contracts_and_the_handler_hooks() {
    let v2 = Contract::from_bytes(
        std::str::from_utf8(CONTRACT)
            .expect("text")
            .replace("\"version\":\"1\"", "\"version\":\"2\"")
            .into_bytes(),
    )
    .expect("v2");
    struct Hooked(Arc<std::sync::Mutex<Vec<String>>>);
    impl Handler for Hooked {
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({"version": request.contract.version, "features": request.features, "run": request.run}).into())
        }
        fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            if info.run == Some("refuse") {
                return Err(Refused("not today".into()));
            }
            let mut granted = Map::new();
            granted.insert("x.feature".into(), json!({"granted": true}));
            granted.insert("not.asked".into(), json!({}));
            Ok(granted)
        }
        fn close(&mut self, reason: &str) {
            self.0.lock().expect("lock").push(reason.to_owned());
        }
    }
    let log = Arc::new(std::sync::Mutex::new(Vec::new()));
    let make =
        || Owner::with_contracts(vec![contract(), v2.clone()], Hooked(log.clone())).expect("owner");
    let mut features = Map::new();
    features.insert("x.feature".into(), json!({}));
    let mut refused = memory_of(make(), false, 0).with_run("refuse");
    let mut refused_v2 = Client::new(
        Memory {
            owner: make(),
            inbox: VecDeque::new(),
            drop_responses: 0,
            lossy: false,
        },
        &v2,
    )
    .with_run("refuse");
    assert!(matches!(refused_v2.open(), Err(Error::Rejected { code, .. }) if code == "refused"));
    let _ = refused.open();
    let mut client = Client::new(
        Memory {
            owner: make(),
            inbox: VecDeque::new(),
            drop_responses: 0,
            lossy: false,
        },
        &v2,
    )
    .with_run("r1")
    .with_features(features);
    client.open().expect("open");
    assert_eq!(
        client.enabled().get("x.feature"),
        Some(&json!({"granted": true}))
    );
    assert!(client.enabled().get("not.asked").is_none());
    let reply = client.call("echo", json!({}), &[]).expect("call");
    assert_eq!(reply.message["body"]["version"], "2");
    assert_eq!(reply.message["body"]["run"], "r1");
    client.channel_mut().owner.finish("lost");
    client.channel_mut().owner.finish("lost");
    assert_eq!(*log.lock().expect("lock"), vec!["lost".to_owned()]);
}

#[test]
fn the_request_schema_of_the_contract() {
    let typed = Contract::from_bytes(
        br#"{"ncp_contract":1,"application":"echo","version":"3","operations":{"echo":{"ncp.schema":{"request":{"type":"object","required":["v"],"properties":{"v":{"ncp.array":{"dtype":"f64","shape":[null,3]}}}}}}},"streams":{}}"#.to_vec(),
    )
    .expect("typed");
    let mut client = Client::new(
        Memory {
            owner: Owner::new(typed.clone(), Echo::default()).with_observer(quiet()),
            inbox: VecDeque::new(),
            drop_responses: 0,
            lossy: false,
        },
        &typed,
    );
    client.open().expect("open");
    let good = Array::new(frame::Dtype::F64, vec![2, 3], vec![0; 48]).expect("array");
    client
        .call("echo", json!({"v": good.reference(0)}), &[good])
        .expect("call");
    let bad = Array::from_f64(&[1.0, 2.0, 3.0]);
    match client.call("echo", json!({"v": bad.reference(0)}), &[bad]) {
        Err(Error::Declined { code, detail, .. }) => {
            assert_eq!(code, "body_invalid");
            assert!(detail.contains("shape"), "{detail}");
        }
        other => panic!("expected declined, got {other:?}"),
    }
}

/// A Rust client over TCP with a transcript of every frame; the transcript verifies.
#[test]
fn tcp_session_with_transcripts() {
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || owner(Echo::default(), MAX_BOUND),
        Limits::default(),
    )
    .expect("server");
    let directory = scratch("tcp");
    let path = directory.join("client.ncpt");
    let tap = Arc::new(ncp::Tap::create(&path).expect("tap"));
    let channel = ncp::connect_tcp(server.address(), false)
        .expect("connect")
        .with_tap(tap.clone());
    let mut client = Client::new(channel, &contract());
    client.open().expect("open");
    let arrays = all_dtypes();
    client
        .call("echo", json!({"v": array_body(&arrays)}), &arrays)
        .expect("call");
    assert!(matches!(
        client.call("echo", json!({"invalid": true}), &[]),
        Err(Error::Declined { .. })
    ));
    client.close().expect("close");
    tap.close().expect("close the transcript");
    let report = transcript::verify(&path, None).expect("verify");
    assert!(report.ok(), "{report:?}");
    assert_eq!((report.closed, report.chain_ok), (true, Some(true)));
    let session = &report.sessions[0];
    assert_eq!(
        (
            session.role.as_str(),
            session.requests,
            session.declined,
            session.complete
        ),
        ("client", 4, 1, true)
    );
    server.stop(Duration::from_secs(1));
}

#[test]
fn transcripts_detect_tampering() {
    let directory = scratch("tamper");
    let path = directory.join("t.ncpt");
    let tap = Arc::new(ncp::Tap::create(&path).expect("tap"));
    {
        let mut client = memory(Echo::default(), false, 0);
        // Record by hand around the memory channel.
        let state_tap = tap.clone();
        client.open().expect("open");
        let reply = client.call("echo", json!({"n": 1}), &[]).expect("call");
        state_tap
            .record(transcript::SENT, &reply.frame)
            .expect("record");
    }
    tap.close().expect("close");
    let mut data = std::fs::read(&path).expect("read");
    let end = data.len();
    data[end - 40] ^= 1; // inside the last chain value or the end record
    std::fs::write(&path, &data).expect("write");
    let report = transcript::verify(&path, None).expect("verify");
    assert_eq!(report.chain_ok, Some(false));
    std::fs::write(&path, &data[..end - 10]).expect("write");
    let report = transcript::verify(&path, None).expect("verify");
    assert!(report.truncated_at.is_some());
    assert!(!report.ok());
}

#[test]
fn a_tap_records_a_frame_before_sending_it_and_a_dropped_tap_closes() {
    let directory = scratch("tap");
    let path = directory.join("t.ncpt");
    let frame_bytes = frame::encode(&json!({"a": 1}), &[]).expect("frame");
    {
        let tap = ncp::Tap::create(&path).expect("tap");
        tap.record(transcript::SENT, &frame_bytes).expect("record");
    }
    let read = transcript::read(&path).expect("read");
    assert_eq!(read.records.len(), 1);
    assert!(read.closed, "dropping the tap writes the end record");
    let path = directory.join("forgotten.ncpt");
    let tap = ncp::Tap::create(&path).expect("tap");
    tap.record(transcript::SENT, &frame_bytes).expect("record");
    std::mem::forget(tap); // as if the program died
    let report = transcript::verify(&path, None).expect("verify");
    assert!(!report.closed);
    assert!(report.problems.iter().any(|p| p.contains("no end record")));
}

#[test]
fn a_keyed_transcript_and_an_authenticated_session() {
    let key = Key::new((0..32).collect()).expect("key");
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        {
            let key = key.clone();
            move || owner(Echo::default(), MAX_BOUND).with_key(key.clone())
        },
        Limits::default(),
    )
    .expect("server");
    let mut client = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    )
    .with_key(key.clone());
    client.open().expect("open");
    client.call("echo", json!({"a": 1}), &[]).expect("call");
    client.close().expect("close");
    let mut stranger = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    );
    let (code, _) = ended(stranger.open());
    assert!(
        code == "local.bad_frame" || code == "local.closed",
        "{code}"
    );
    server.stop(Duration::from_secs(1));
}

#[test]
fn a_bad_frame_ends_a_tcp_connection() {
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || owner(Echo::default(), MAX_BOUND),
        Limits::default(),
    )
    .expect("server");
    let mut stream = std::net::TcpStream::connect(server.address()).expect("connect");
    let mut damaged = frame::encode(&json!({"a": "x".repeat(70_000)}), &[]).expect("frame");
    damaged[40_000] ^= 1;
    std::io::Write::write_all(&mut stream, &damaged).expect("write");
    let mut channel = ncp::tcp_channel(stream).expect("channel");
    let reply = channel
        .receive_frame(MAX_BOUND)
        .expect("bad-frame response");
    let message = frame::decode(reply, MAX_BOUND).expect("decode").message;
    assert_eq!(
        (message["code"].as_str(), message["session"].is_null()),
        (Some("bad_frame"), true)
    );
    server.stop(Duration::from_secs(1));
}

#[test]
fn a_full_server_refuses_an_open_and_stop_sends_the_shutdown_response() {
    let limits = Limits {
        max_sessions: 1,
        ..Limits::default()
    };
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || owner(Echo::default(), MAX_BOUND),
        limits,
    )
    .expect("server");
    let mut first = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    );
    first.open().expect("open");
    let mut second = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    );
    assert!(matches!(second.open(), Err(Error::Rejected { code, .. }) if code == "refused"));
    first.call("echo", json!({}), &[]).expect("call");
    server.stop(Duration::from_secs(2));
    let (code, verdict) = ended(first.call("echo", json!({}), &[]));
    assert!(
        (code.as_str(), verdict) == ("shutdown", Executed::No)
            || (code.as_str(), verdict) == ("local.closed", Executed::Unknown),
        "{code} {verdict}"
    );
}

#[test]
fn an_idle_session_ends_with_the_shutdown_response() {
    let limits = Limits {
        idle_timeout: Some(Duration::from_millis(200)),
        ..Limits::default()
    };
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || owner(Echo::default(), MAX_BOUND),
        limits,
    )
    .expect("server");
    let mut client = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    );
    client.open().expect("open");
    std::thread::sleep(Duration::from_millis(500));
    let (code, _) = ended(client.call("echo", json!({}), &[]));
    assert!(code == "shutdown" || code == "local.closed", "{code}");
    server.stop(Duration::from_secs(1));
}

#[test]
fn remote_addresses_need_permission() {
    assert!(ncp::connect_tcp("192.0.2.1:1", false).is_err());
    assert!(ncp::listen_tcp("0.0.0.0:0", false).is_err());
    assert!(ncp::listen_tcp("127.0.0.1:0", false).is_ok());
}

#[test]
fn the_digest_check_can_be_turned_off_only_on_local_links() {
    let mut client = memory(Echo::default(), false, 0).without_digest_check();
    client.open().expect("open");
    client.call("echo", json!({"a": 1}), &[]).expect("call");
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || owner(Echo::default(), MAX_BOUND).without_digest_check(),
        Limits::default(),
    )
    .expect("server");
    let mut client = Client::new(
        ncp::connect_tcp(server.address(), false).expect("connect"),
        &contract(),
    );
    assert!(matches!(client.open(), Err(Error::Ended { .. })));
    server.stop(Duration::from_secs(1));
    let tcp = ncp::connect_tcp(
        ncp::listen_tcp("127.0.0.1:0", false)
            .expect("listen")
            .local_addr()
            .expect("address"),
        false,
    )
    .expect("connect");
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        Client::new(tcp, &contract()).without_digest_check()
    }));
    assert!(
        result.is_err(),
        "the client refuses to turn the comparison off over TCP"
    );
}

#[test]
fn call_all_sends_every_request_before_it_reads_a_response() {
    let log = Arc::new(std::sync::Mutex::new(Vec::new()));
    struct Logged {
        name: usize,
        inner: Memory<Echo>,
        log: Arc<std::sync::Mutex<Vec<(&'static str, usize)>>>,
    }
    impl Channel for Logged {
        fn lossy(&self) -> bool {
            false
        }
        fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
            self.log.lock().expect("lock").push(("send", self.name));
            self.inner.send(frame_bytes)
        }
        fn receive(&mut self, bound: usize) -> Result<Vec<u8>, ChannelError> {
            self.log.lock().expect("lock").push(("receive", self.name));
            self.inner.receive(bound)
        }
    }
    let mut clients: Vec<Client<Logged>> = (0..4)
        .map(|name| {
            let inner = Memory {
                owner: owner(Echo::default(), MAX_BOUND),
                inbox: VecDeque::new(),
                drop_responses: 0,
                lossy: false,
            };
            Client::new(
                Logged {
                    name,
                    inner,
                    log: log.clone(),
                },
                &contract(),
            )
        })
        .collect();
    for client in &mut clients {
        client.open().expect("open");
    }
    log.lock().expect("lock").clear();
    let results = ncp::call_all(
        &mut clients,
        "echo",
        (0..4).map(|i| json!({"agent": i})).collect(),
    );
    for (i, result) in results.iter().enumerate() {
        assert_eq!(
            result.as_ref().expect("result").message["body"],
            json!({"agent": i})
        );
    }
    let expected: Vec<(&str, usize)> = (0..4)
        .map(|i| ("send", i))
        .chain((0..4).map(|i| ("receive", i)))
        .collect();
    assert_eq!(*log.lock().expect("lock"), expected);
}

#[test]
fn call_all_returns_the_error_of_one_session_in_its_place() {
    let mut clients: Vec<_> = (0..3)
        .map(|_| memory(Echo::default(), false, 0).with_bound(HANDSHAKE_BOUND))
        .collect();
    for client in &mut clients {
        client.open().expect("open");
    }
    let _ = clients[1].call("fail", json!({}), &[]);
    let results = ncp::call_all(
        &mut clients,
        "echo",
        vec![
            json!({"n": 0}),
            json!({"n": 1}),
            json!({"blob": "x".repeat(HANDSHAKE_BOUND)}),
        ],
    );
    assert!(results[0].is_ok());
    assert!(matches!(results[1], Err(Error::Usage(_))));
    assert!(matches!(results[2], Err(Error::Usage(_))));
}

#[test]
fn the_subscriber_applies_its_bound_to_each_frame() {
    // Rule 8.4: a frame over the subscriber's bound is a bad frame, and changes no stream state.
    let identity = contract().identity;
    let mut publisher = Publisher::exact("big", &identity).expect("publisher");
    let blob = ncp::Array::new(
        ncp::Dtype::U8,
        vec![HANDSHAKE_BOUND as u64],
        vec![0; HANDSHAKE_BOUND],
    )
    .expect("array");
    let large = publisher
        .publish(json!({"blob": blob.reference(0)}), &[blob])
        .expect("publish");
    assert!(large.len() > HANDSHAKE_BOUND);
    let mut subscriber = Subscriber::new([identity]).with_bound(HANDSHAKE_BOUND);
    assert_eq!(subscriber.receive(large).0, Delivery::BadFrame);
    let next = publisher.publish(json!({}), &[]).expect("publish");
    assert_eq!(subscriber.receive(next).0, Delivery::Joined { end: false });
}

#[test]
fn streams_detect_loss_repeats_conflicts_and_forgery() {
    let identity = contract().identity;
    let mut publisher = Publisher::new("sensor", &identity).expect("publisher");
    assert!(publisher.stream().starts_with("sensor/") && publisher.stream().len() == 23);
    let frames: Vec<Vec<u8>> = (0..6)
        .map(|i| publisher.publish(json!({"i": i}), &[]).expect("publish"))
        .collect();
    let mut subscriber = Subscriber::new([identity.clone()]);
    let mut receive = |f: &Vec<u8>| subscriber.receive(f.clone()).0;
    assert_eq!(
        receive(&frames[0]),
        Delivery::Accepted {
            lost: 0,
            end: false
        }
    );
    assert_eq!(receive(&frames[0]), Delivery::Repeat);
    assert_eq!(
        receive(&frames[3]),
        Delivery::Accepted {
            lost: 2,
            end: false
        }
    );
    let mut forger = Publisher::exact(publisher.stream(), &identity).expect("forger");
    let forged: Vec<Vec<u8>> = (0..6)
        .map(|i| forger.publish(json!({"forged": i}), &[]).expect("publish"))
        .collect();
    assert_eq!(receive(&forged[3]), Delivery::Conflict);
    assert_eq!(receive(&forged[4]), Delivery::BrokenChain);
    assert_eq!(
        receive(&frames[4]),
        Delivery::Accepted {
            lost: 0,
            end: false
        }
    );
    let mut damaged = frames[5].clone();
    damaged[20] ^= 1;
    assert_eq!(receive(&damaged), Delivery::BadFrame);
    let end = publisher.end(json!({"why": "done"})).expect("end");
    assert!(publisher.publish(json!({}), &[]).is_err());
    let mut late = Subscriber::new([identity.clone()]);
    assert_eq!(late.receive(end).0, Delivery::Joined { end: true });
    let mut stranger = Publisher::new("other", &"0".repeat(64)).expect("publisher");
    assert_eq!(
        receive(&stranger.publish(json!({}), &[]).expect("publish")),
        Delivery::UnknownContract
    );
}

fn python_echo_owner() -> Option<std::process::Command> {
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python/tests/echo_owner.py");
    let available = std::process::Command::new("python3")
        .arg("-c")
        .arg("import sys; sys.exit(sys.version_info < (3, 11))")
        .status()
        .is_ok_and(|s| s.success());
    if !available {
        eprintln!("python3 >= 3.11 not found: skipping the cross-language test");
        return None;
    }
    let mut command = std::process::Command::new("python3");
    command.arg("-I").arg(script);
    Some(command)
}

fn python_contract() -> Contract {
    Contract::from_bytes(
        br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}"#
            .to_vec(),
    )
    .expect("contract")
}

#[test]
fn rust_client_with_the_python_owner() {
    let Some(command) = python_echo_owner() else {
        return;
    };
    let mut client = Client::new(ncp::spawn(command).expect("spawn"), &python_contract());
    let opened = client.open().expect("open");
    assert!(opened["implementation"]
        .as_str()
        .is_some_and(|s| s.starts_with("ncp-python/")));
    let arrays = all_dtypes();
    let reply = client
        .call(
            "echo",
            json!({"v": array_body(&arrays), "text": "é😀", "n": 9007199254740991_i64}),
            &arrays,
        )
        .expect("call");
    assert_eq!(reply.message["body"]["text"], "é😀");
    assert_eq!(reply.message["body"]["n"], 9007199254740991_i64);
    for (index, array) in arrays.iter().enumerate() {
        assert_eq!(
            reply.array_bytes(index).expect("bytes"),
            &array.data[..],
            "array {index}"
        );
    }
    assert!(matches!(
        client.call("echo", json!({"invalid": true}), &[]),
        Err(Error::Declined { .. })
    ));
    client.ping().expect("ping");
    assert_eq!(
        ended(client.call("fail", json!({}), &[])),
        ("owner_failure".into(), Executed::Unknown)
    );
    client.close().expect("close");
}

fn scratch(name: &str) -> PathBuf {
    // Short, so that a Unix domain socket path inside it stays below the system limit.
    let base = if cfg!(unix) {
        PathBuf::from("/tmp")
    } else {
        std::env::temp_dir()
    };
    let directory = base.join(format!("ncp-{name}-{}", &ncp::random_session()[..8]));
    std::fs::create_dir_all(&directory).expect("scratch directory");
    directory
}

/// Executes `echo` only after a long sleep: an owner that stalls.
struct Stalling;

impl Handler for Stalling {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        std::thread::sleep(Duration::from_secs(3));
        Ok(request.body.clone().into())
    }
}

#[test]
fn a_time_limit_ends_a_stalled_call() {
    let mut server = ncp::serve_tcp(
        "127.0.0.1:0",
        false,
        || Owner::new(contract(), Stalling),
        Limits::default(),
    )
    .expect("server");
    let mut channel = ncp::connect_tcp(server.address(), false).expect("connect");
    channel.set_timeout(Some(Duration::from_millis(200)));
    let mut client = Client::new(channel, &contract());
    client.open().expect("open");
    let started = Instant::now();
    assert_eq!(
        ended(client.call("echo", json!({}), &[])),
        ("local.timeout".into(), Executed::Unknown)
    );
    assert!(
        started.elapsed() < Duration::from_secs(2),
        "the time limit was not kept"
    );
    server.stop(Duration::from_millis(10));
}

#[cfg(unix)]
#[test]
fn a_child_on_a_socket_pair_takes_a_time_limit() {
    let mut command = std::process::Command::new("sleep");
    command.arg("5");
    let mut channel = ncp::spawn_unix(command)
        .expect("spawn")
        .with_grace(Duration::from_millis(10));
    channel.set_timeout(Some(Duration::from_millis(200)));
    let mut client = Client::new(channel, &contract());
    let started = Instant::now();
    assert_eq!(
        ended(client.open()),
        ("local.timeout".into(), Executed::Unknown)
    );
    assert!(started.elapsed() < Duration::from_secs(2));
    let mut channel = client;
    let _ = channel.close();
}

#[cfg(unix)]
#[test]
fn a_child_channel_ends_its_child() {
    let Some(command) = python_echo_owner() else {
        return;
    };
    let mut client = Client::new(ncp::spawn_unix(command).expect("spawn"), &python_contract());
    client.open().expect("open");
    assert_eq!(
        client
            .call("echo", json!({"pair": true}), &[])
            .expect("call")
            .message["body"],
        json!({"pair": true})
    );
    client.close().expect("close");
    assert!(client
        .channel_mut()
        .exit_status()
        .is_some_and(|s| s.success()));
}

#[cfg(unix)]
#[test]
fn a_unix_server_serves_sessions_and_removes_its_socket() {
    use std::os::unix::fs::PermissionsExt;
    let directory = scratch("unix");
    let path = directory.join("owner.sock");
    let mut server = ncp::serve_unix(
        &path,
        || owner(Echo::default(), MAX_BOUND),
        Limits::default(),
    )
    .expect("server");
    assert_eq!(
        std::fs::metadata(&path)
            .expect("socket")
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    let mut clients: Vec<_> = (0..3)
        .map(|_| Client::new(ncp::connect_unix(&path).expect("connect"), &contract()))
        .collect();
    for (i, client) in clients.iter_mut().enumerate() {
        client.open().expect("open");
        assert_eq!(
            client
                .call("echo", json!({"i": i}), &[])
                .expect("call")
                .message["body"],
            json!({"i": i})
        );
        client.close().expect("close");
    }
    server.stop(Duration::from_secs(1));
    assert!(!path.exists());
}

#[test]
fn encoders_refuse_frames_that_receivers_must_reject() {
    assert!(frame::encode(&json!({"n": 9007199254740992_u64}), &[]).is_err());
    assert!(frame::encode(&json!([1]), &[]).is_err());
    assert!(frame::encode(&json!({"att": []}), &[]).is_err());
    let mut deep = json!(1);
    for _ in 0..63 {
        deep = json!([deep]);
    }
    assert!(frame::encode(&json!({"d": deep.clone()}), &[]).is_ok());
    assert!(frame::encode(&json!({"d": [deep]}), &[]).is_err());
    let big = json!({"a": "x".repeat(frame::MAX_JSON)});
    assert!(matches!(
        frame::encode_with(&big, &[], None, None),
        Err(frame::EncodeError::TooLarge(t)) if t.json
    ));
    // A JSON region of the largest size, 1 MiB minus 4 bytes, still decodes.
    let largest =
        frame::encode(&json!({"a": "x".repeat(frame::MAX_JSON - 16)}), &[]).expect("frame");
    assert!(frame::decode(largest, MAX_BOUND).is_ok());
}

#[test]
fn the_json_padding_is_exact() {
    let make = |text: &[u8], pad: &[u8]| {
        let mut frame_bytes = b"NCP\x02".to_vec();
        frame_bytes.extend_from_slice(&((text.len() + pad.len()) as u32).to_be_bytes());
        frame_bytes.extend_from_slice(&0u32.to_be_bytes());
        frame_bytes.extend_from_slice(text);
        frame_bytes.extend_from_slice(pad);
        let digest = frame::digest_of(None, &[&frame_bytes]);
        frame_bytes.extend_from_slice(&digest);
        frame_bytes
    };
    assert!(frame::decode(make(br#"{"a":1}"#, b"     "), MAX_BOUND).is_ok());
    assert!(frame::decode(make(br#"{"a":1}"#, &[b' '; 9]), MAX_BOUND).is_err());
    assert!(frame::decode(make(br#"{"a":1}"#, b"\t\n\r\n "), MAX_BOUND).is_err());
    assert!(frame::decode(make(br#"        {"a":1}"#, b""), MAX_BOUND).is_err());
}

#[test]
fn the_frame_identity_of_short_input_does_not_panic() {
    assert_eq!(frame::identity(b"ab"), "6162");
}

#[test]
fn unknown_codes_are_handled_by_outcome() {
    struct Scripted {
        script: VecDeque<(&'static str, Option<&'static str>, Value)>,
        inbox: VecDeque<Vec<u8>>,
    }
    impl Channel for Scripted {
        fn lossy(&self) -> bool {
            false
        }
        fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
            let request = frame::decode(frame_bytes.to_vec(), MAX_BOUND)
                .expect("request")
                .message;
            let (outcome, code, body) = self.script.pop_front().expect("script");
            let message = json!({"ncp": 2, "session": request["session"], "seq": request["seq"],
                                 "request": frame::identity(frame_bytes), "outcome": outcome, "code": code, "body": body});
            self.inbox
                .push_back(frame::encode(&message, &[]).expect("encode"));
            Ok(())
        }
        fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
            self.inbox.pop_front().ok_or(ChannelError::Timeout)
        }
    }
    let open =
        json!({"bound": HANDSHAKE_BOUND, "nonce": "0".repeat(32), "features": {}, "later": [1]});
    let scripted = |replies: Vec<(&'static str, Option<&'static str>, Value)>| {
        Client::new(
            Scripted {
                script: VecDeque::from(replies),
                inbox: VecDeque::new(),
            },
            &contract(),
        )
        .with_bound(HANDSHAKE_BOUND)
    };
    let mut client = scripted(vec![
        ("ok", None, open.clone()),
        ("declined", Some("later_decline"), json!({})),
        ("rejected", Some("later_reason"), json!({})),
    ]);
    assert_eq!(client.open().expect("open")["later"], json!([1]));
    assert!(
        matches!(client.call("echo", json!({}), &[]), Err(Error::Declined { code, .. }) if code == "later_decline")
    );
    assert_eq!(client.state().seq, 1);
    // Rule 7.6.4: a rejection of a request other than open ends the session, possibly executed.
    assert_eq!(
        ended(client.call("echo", json!({}), &[])),
        ("later_reason".into(), Executed::Unknown)
    );
    assert!(client.state().ended);
    let mut client = scripted(vec![
        ("ok", None, open),
        ("ended", Some("later_end"), json!({})),
    ]);
    client.open().expect("open");
    assert_eq!(
        ended(client.call("echo", json!({}), &[])),
        ("later_end".into(), Executed::Unknown)
    );
}

struct World {
    position: i64,
}

impl Handler for World {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        self.position += request.body["dx"].as_i64().unwrap_or(0);
        if request.op == "fail" {
            return Err("the world failed half way".into()); // after it changed its state
        }
        Ok(json!({"position": self.position}).into())
    }
}

impl Stepper for World {
    fn state(&self) -> Option<String> {
        Some(format!("p{}", self.position))
    }
}

#[test]
fn lockstep_steps_carry_the_tick_and_a_new_session_tells_whether_the_last_step_ran() {
    for (lose_response, expected) in [(true, Executed::Yes), (false, Executed::No)] {
        let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
        let mut features = Map::new();
        features.insert(ncp::lockstep::FEATURE.into(), json!({}));
        let first = Client::new(
            Memory {
                owner: Owner::new(contract(), lockstep.share()),
                inbox: VecDeque::new(),
                drop_responses: 0,
                lossy: false,
            },
            &contract(),
        )
        .with_features(features.clone());
        let mut stepper = LockstepClient::new(first).expect("lockstep");
        let result = stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
        assert_eq!(result.message["body"]["position"], 2);
        assert_eq!((stepper.tick, stepper.state.as_deref()), (1, Some("p2")));
        if lose_response {
            stepper.client().channel_mut().drop_responses = 1; // executed, answer lost
        } else {
            stepper.client().channel_mut().inbox.clear(); // the request never arrives: a timeout
        }
        let outcome = if lose_response {
            stepper.step("echo", json!({"dx": 1}), &[])
        } else {
            // Drop the request: an owner that is gone.
            let pending_error = {
                let channel = stepper.client().channel_mut();
                channel.lossy = false;
                channel.drop_responses = 0;
                channel.owner.stop();
                stepper.step("echo", json!({"dx": 1}), &[])
            };
            pending_error
        };
        let error = outcome.expect_err("the step's answer is lost");
        if lose_response {
            assert_eq!(error.executed(), Executed::Unknown);
            let (tick, identity) = stepper.uncertain.clone().expect("possibly executed");
            assert_eq!(tick, 2);
            assert!(identity.is_some());
            let fresh = Client::new(
                Memory {
                    owner: Owner::new(contract(), lockstep.share()),
                    inbox: VecDeque::new(),
                    drop_responses: 0,
                    lossy: false,
                },
                &contract(),
            )
            .with_features(features.clone());
            assert_eq!(stepper.recover(fresh).expect("recover"), expected);
            assert_eq!(stepper.tick, 2);
            stepper
                .step("echo", json!({"dx": 10}), &[])
                .expect("step after recovery");
            assert_eq!(lockstep.clock().tick, 3);
        } else {
            assert_eq!(error.executed(), Executed::No); // shutdown: the owner stopped first
            assert_eq!(lockstep.clock().tick, 1);
        }
    }
}

/// A channel that holds back the requests once the connection breaks, as a slow network can.
struct Held<H: Handler> {
    owner: Owner<H>,
    inbox: VecDeque<Vec<u8>>,
    held: Vec<Vec<u8>>,
    broken: bool,
}

impl<H: Handler> Channel for Held<H> {
    fn lossy(&self) -> bool {
        false
    }
    fn local(&self) -> bool {
        true
    }
    fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
        if self.broken {
            self.held.push(frame_bytes.to_vec());
            return Err(std::io::Error::other("the connection broke"));
        }
        let response = self
            .owner
            .handle(frame_bytes.to_vec())
            .map_err(std::io::Error::other)?;
        self.inbox.push_back(response.to_vec());
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn held_session(lockstep: &Lockstep<World>, feature: bool) -> Client<Held<Lockstep<World>>> {
    let mut features = Map::new();
    if feature {
        features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    }
    Client::new(
        Held {
            owner: Owner::new(contract(), lockstep.share()),
            inbox: VecDeque::new(),
            held: Vec::new(),
            broken: false,
        },
        &contract(),
    )
    .with_features(features)
    .with_observer(quiet())
}

/// The outcome, code, and detail of an owner's response.
fn answer(response: &[u8]) -> (String, String, String) {
    let message = frame::decode(response.to_vec(), MAX_BOUND)
        .expect("response")
        .message;
    let text = |v: &Value| v.as_str().unwrap_or_default().to_owned();
    (
        text(&message["outcome"]),
        text(&message["code"]),
        text(&message["body"]["detail"]),
    )
}

#[test]
fn a_session_that_takes_over_the_ticks_fences_the_steps_of_earlier_sessions() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo", "fail"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    // The connection breaks while the second step is on its way.
    stepper.client().channel_mut().broken = true;
    let error = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    assert_eq!(error.executed(), Executed::Unknown);
    assert_eq!(stepper.uncertain.as_ref().map(|u| u.0), Some(2));
    let held = std::mem::take(&mut stepper.client().channel_mut().held);
    let mut old = std::mem::replace(
        &mut stepper.client().channel_mut().owner,
        Owner::new(contract(), lockstep.share()),
    );
    // Recovery opens a new session, which takes over the ticks: the step did not run.
    assert_eq!(
        stepper
            .recover(held_session(&lockstep, true))
            .expect("recover"),
        Executed::No
    );
    assert_eq!(stepper.tick, 1);
    // The delayed request reaches the old session after the recovery: it never runs.
    let (outcome, code, detail) = answer(&old.handle(held[0].clone()).expect("a response"));
    assert_eq!(
        (outcome.as_str(), code.as_str()),
        ("declined", "body_invalid")
    );
    assert!(detail.contains("does not hold the ticks"), "{detail}");
    assert_eq!(lockstep.clock().tick, 1);
    let result = stepper
        .step("echo", json!({"dx": 10}), &[])
        .expect("the step again, in the new session");
    assert_eq!(result.message["body"]["position"], 12);
    // A session that did not ask for the feature cannot step.
    let mut plain = held_session(&lockstep, false);
    plain.open().expect("open");
    let refused = plain.call(
        "echo",
        json!({"dx": 1, "ncp.tick": {"tick": 3, "state": "p12"}}),
        &[],
    );
    assert!(
        matches!(&refused, Err(Error::Declined { detail, .. }) if detail.contains("does not hold the ticks")),
        "{refused:?}"
    );
}

#[test]
fn a_lockstep_step_whose_application_fails_counts_as_executed() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo", "fail"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    let error = stepper
        .step("fail", json!({"dx": 4}), &[])
        .expect_err("the application failed");
    assert_eq!(
        (error.code(), error.executed()),
        (Some("owner_failure"), Executed::Unknown)
    );
    assert_eq!(lockstep.clock().tick, 1);
    // The world moved before it failed, so the recovery must say that the step ran.
    assert_eq!(
        stepper
            .recover(held_session(&lockstep, true))
            .expect("recover"),
        Executed::Yes
    );
    assert_eq!((stepper.tick, stepper.state.as_deref()), (1, Some("p4")));
}

#[test]
fn a_recovery_that_finds_the_step_of_another_session_gives_no_verdict() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut first = LockstepClient::new(held_session(&lockstep, true)).expect("first");
    first.client().channel_mut().broken = true;
    first
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    // Another client takes over the ticks and makes the step with the same tick.
    let mut second = LockstepClient::new(held_session(&lockstep, true)).expect("second");
    second
        .step("echo", json!({"dx": 5}), &[])
        .expect("the other step");
    let verdict = first.recover(held_session(&lockstep, true));
    assert!(matches!(verdict, Err(Error::Usage(_))), "{verdict:?}");
    assert!(first.uncertain.is_some());
}

#[test]
fn a_takeover_waits_for_a_checked_step_and_reads_its_tick() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let contract = contract();
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let mut first = lockstep.share();
    first
        .open(&OpenInfo {
            session: "first",
            contract: &contract,
            run: None,
            features: &features,
        })
        .expect("open");
    let body = json!({"dx": 3, "ncp.tick": {"tick": 1, "state": null}});
    let decoded = frame::Decoded {
        message: json!({}),
        arrays: Vec::new(),
        identity: "r1".into(),
        frame: Arc::new(Vec::new()),
    };
    let request = Request {
        op: "echo",
        body: &body,
        seq: 1,
        session: "first",
        identity: "r1",
        contract: &contract,
        run: None,
        features: &features,
        decoded: &decoded,
    };
    first.validate(&request).expect("the step is checked");
    // A session that takes over the ticks now waits until the checked step has run.
    let mut second = lockstep.share();
    let waiting = std::thread::spawn(move || {
        let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
        let mut features = Map::new();
        features.insert(ncp::lockstep::FEATURE.into(), json!({}));
        second
            .open(&OpenInfo {
                session: "second",
                contract: &contract,
                run: None,
                features: &features,
            })
            .expect("open")[ncp::lockstep::FEATURE]
            .clone()
    });
    std::thread::sleep(Duration::from_millis(100));
    assert!(!waiting.is_finished(), "the takeover did not wait");
    first.execute(&request).expect("the step runs");
    assert_eq!(
        waiting.join().expect("the takeover"),
        json!({"tick": 1, "state": "p3", "request": "r1"})
    );
    assert_eq!(lockstep.clock().holder.as_deref(), Some("second"));
}
