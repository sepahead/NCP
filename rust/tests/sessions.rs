//! Sessions end to end: in-memory and lossy channels, TCP, Unix domain sockets, child processes,
//! servers, transcripts, streams, profiles, and the Python reference owner when `python3` is
//! available.

use ncp::frame::{self, Array, Key, HANDSHAKE_BOUND, MAX_BOUND};
use ncp::{
    conflict, declined, events, transcript, AppError, Channel, ChannelError, Client, Contract,
    Delivery, Error, Executed, Handler, Invalid, Limits, Lockstep, LockstepClient, OpenInfo, Owner,
    Publisher, Refused, Reply, Request, Stepper, Subscriber,
};
use serde_json::{json, Map, Value};
use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
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

/// A handler that declines every request as its function says.
struct Declining(fn(&Value) -> Invalid);

impl Handler for Declining {
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        Err((self.0)(request.body))
    }
    fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
        Ok(json!({}).into())
    }
}

/// A decline, and the code and the reason that the client sees.
type DeclineCase = (fn(&Value) -> Invalid, &'static str, Option<&'static str>);

/// The contract of `echo` with the reasons of its operation (section 11, rule 6).
const LISTED: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{"ncp.reasons":["echo.busy"]}},"streams":{}}"#;

fn declining(decline: fn(&Value) -> Invalid, max_bound: usize) -> Client<Memory<Declining>> {
    let listed = Contract::from_bytes(LISTED.to_vec()).expect("contract");
    let owner = Owner::new(listed.clone(), Declining(decline))
        .with_max_bound(max_bound)
        .with_observer(quiet());
    let channel = Memory {
        owner,
        inbox: VecDeque::new(),
        drop_responses: 0,
        lossy: false,
    };
    Client::new(channel, &listed).with_observer(quiet())
}

#[test]
fn a_conflict_names_its_reason_and_the_facts_of_a_profile() {
    // Rule 7.3.12 and section 7.5: the application chooses the code and the reason; the facts of
    // a profile ride along, and the owner leaves them out, never the reason, when they do not fit.
    let mut client = declining(
        |body| {
            let mut facts = Map::new();
            let fact = if body["big"] == true {
                json!("x".repeat(70_000))
            } else {
                json!({"next": 4})
            };
            facts.insert("ncp.echo".into(), fact);
            conflict("echo.busy", "busy").members(facts)
        },
        HANDSHAKE_BOUND,
    );
    client.open().expect("open");
    let error = client.call("echo", json!({}), &[]).expect_err("declined");
    assert_eq!(error.code(), Some("conflict"));
    assert_eq!(error.reason(), Some("echo.busy"));
    assert_eq!(error.executed(), Executed::No);
    match &error {
        Error::Declined { body, .. } => assert_eq!(
            body,
            &json!({"detail": "busy", "ncp.echo": {"next": 4}, "ncp.reason": "echo.busy"})
        ),
        other => panic!("expected declined, got {other:?}"),
    }
    match client.call("echo", json!({"big": true}), &[]) {
        Err(Error::Declined { code, body, .. }) => {
            assert_eq!(code, "conflict");
            assert_eq!(body, json!({"detail": "busy", "ncp.reason": "echo.busy"}));
        }
        other => panic!("expected declined, got {other:?}"),
    }
    assert_eq!(client.state().seq, 2);
}

#[test]
fn a_decline_that_ncp_cannot_send_ends_the_session() {
    // A reason is a name, and an operation that lists its reasons (section 11, rule 6) gives no
    // other reason of the application. Anything else is a defect while checking: owner_failure.
    let cases: [DeclineCase; 6] = [
        (|_| conflict("Not A Name", "no"), "owner_failure", None),
        (|_| conflict("echo.other", "no"), "owner_failure", None),
        (
            |_| conflict("echo.busy", "no"),
            "conflict",
            Some("echo.busy"),
        ),
        (
            |_| conflict("ncp.profile.reason", "no"),
            "conflict",
            Some("ncp.profile.reason"),
        ),
        (|_| declined("no"), "body_invalid", None),
        (
            |_| declined("no").reason("echo.busy"),
            "body_invalid",
            Some("echo.busy"),
        ),
    ];
    for (decline, code, reason) in cases {
        let mut client = declining(decline, MAX_BOUND);
        client.open().expect("open");
        let error = client.call("echo", json!({}), &[]).expect_err("not ok");
        assert_eq!(error.code(), Some(code));
        assert_eq!(error.reason(), reason);
        assert_eq!(
            matches!(error, Error::Ended { .. }),
            code == "owner_failure"
        );
    }
}

#[test]
fn a_refused_open_names_its_reason() {
    struct Full(&'static str);
    impl Handler for Full {
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            Err(Refused::new("full").reason(self.0))
        }
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
    }
    for (reason, body) in [
        (
            "echo.full",
            json!({"detail": "full", "ncp.reason": "echo.full"}),
        ),
        (
            "Full!",
            json!({"detail": "the application failed to open the session"}),
        ),
    ] {
        let owner = Owner::new(contract(), Full(reason)).with_observer(quiet());
        let channel = Memory {
            owner,
            inbox: VecDeque::new(),
            drop_responses: 0,
            lossy: false,
        };
        let mut client = Client::new(channel, &contract()).with_observer(quiet());
        match client.open() {
            Err(error @ Error::Rejected { .. }) => {
                assert_eq!(error.code(), Some("refused"));
                assert_eq!(error.reason(), body["ncp.reason"].as_str());
                if let Error::Rejected { body: got, .. } = error {
                    assert_eq!(got, body);
                }
            }
            other => panic!("expected a refused open, got {other:?}"),
        }
    }
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
                return Err(Refused::new("not today"));
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
    /// Every frame that the client sent, in order.
    frames: Vec<Vec<u8>>,
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
        self.frames.push(frame_bytes.to_vec());
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
            frames: Vec::new(),
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

/// A stepper whose second step is on its way when its connection breaks.
fn lose_a_step(
    lockstep: &Lockstep<World>,
    session: Option<&str>,
) -> LockstepClient<Held<Lockstep<World>>> {
    let mut client = held_session(lockstep, true);
    if let Some(session) = session {
        client = client.with_session(session);
    }
    let mut stepper = LockstepClient::new(client).expect("lockstep");
    stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    stepper.client().channel_mut().broken = true;
    let error = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    assert_eq!(error.executed(), Executed::Unknown);
    stepper
}

/// The frames that the connection held back, and the owner of the old opening, which the
/// stepper's channel gives up for a fresh one.
fn take_the_old_connection(
    stepper: &mut LockstepClient<Held<Lockstep<World>>>,
    lockstep: &Lockstep<World>,
) -> (Vec<Vec<u8>>, Owner<Lockstep<World>>) {
    let channel = stepper.client().channel_mut();
    let held = std::mem::take(&mut channel.held);
    let old = std::mem::replace(&mut channel.owner, Owner::new(contract(), lockstep.share()));
    (held, old)
}

#[test]
fn a_take_fences_the_steps_of_earlier_openings() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = lose_a_step(&lockstep, None);
    let (held, mut old) = take_the_old_connection(&mut stepper, &lockstep);
    // Recovery opens a new session and takes the ticks: the step did not run.
    assert_eq!(
        stepper
            .recover(held_session(&lockstep, true))
            .expect("recover"),
        Executed::No
    );
    assert_eq!(stepper.tick, 1);
    // The delayed request reaches the old opening after the recovery: it never runs.
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
    let nonce = stepper.client().nonce().map(str::to_owned);
    let clock = lockstep.clock();
    assert_eq!((clock.holder, clock.term), (nonce, 2));
    // A session that did not ask for the feature can neither step nor take.
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
    for op in ["ncp.lockstep.take", "ncp.other.thing"] {
        let refused = plain.call(op, json!({"term": 2}), &[]);
        assert!(
            matches!(&refused, Err(Error::Declined { code, .. }) if code == "unknown_op"),
            "{op}: {refused:?}"
        );
    }
}

#[test]
fn an_open_only_reports_the_clock() {
    // Profile rule 3.3: an open with the feature changes nothing outside its session. A monitor
    // reads the clock without fencing the stepping client, and cannot step itself.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    let result = stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    let mut monitor = held_session(&lockstep, true);
    monitor.open().expect("open");
    assert_eq!(
        monitor.enabled()[ncp::lockstep::FEATURE],
        json!({"tick": 1, "state": "p2", "request": result.message["request"], "term": 1})
    );
    let nonce = stepper.client().nonce().map(str::to_owned);
    assert_eq!(lockstep.clock().holder, nonce);
    let next = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect("the stepper keeps going");
    assert_eq!(next.message["body"]["position"], 3);
    match monitor.call(
        "echo",
        json!({"dx": 1, "ncp.tick": {"tick": 3, "state": "p3"}}),
        &[],
    ) {
        Err(Error::Declined { detail, body, .. }) => {
            assert!(detail.contains("does not hold the ticks"), "{detail}");
            assert_eq!(body[ncp::lockstep::FEATURE], json!({"term": 1}));
        }
        other => panic!("expected declined, got {other:?}"),
    }
}

#[test]
fn a_copy_of_an_old_open_takes_nothing() {
    // Profile rule 3.3 and specification rule 7.1.8. A copy of the first open, replayed on
    // another connection, opens that session again with another nonce and takes nothing. A copy
    // of the old take acknowledges the old open response, so the copy's opening rejects it.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = lose_a_step(&lockstep, None);
    let frames = stepper.client().channel_mut().frames.clone();
    let (held, mut old) = take_the_old_connection(&mut stepper, &lockstep);
    assert_eq!(
        stepper
            .recover(held_session(&lockstep, true))
            .expect("recover"),
        Executed::No
    );
    let holder = lockstep.clock().holder;
    let mut replayed = Owner::new(contract(), lockstep.share()).with_observer(quiet());
    let (outcome, _, _) = answer(&replayed.handle(frames[0].clone()).expect("a response"));
    assert_eq!(outcome, "ok");
    let (outcome, code, _) = answer(&replayed.handle(frames[1].clone()).expect("a response"));
    assert_eq!(
        (outcome.as_str(), code.as_str()),
        ("rejected", "ack_mismatch")
    );
    assert_eq!(lockstep.clock().holder, holder);
    // The delayed step reaches the first opening: it never runs, so "did not run" stays true.
    let (outcome, code, _) = answer(&old.handle(held[0].clone()).expect("a response"));
    assert_eq!(
        (outcome.as_str(), code.as_str()),
        ("declined", "body_invalid")
    );
    let clock = lockstep.clock();
    assert_eq!((clock.tick, clock.state.as_deref()), (1, Some("p2")));
    // And the stepping client keeps going.
    let result = stepper
        .step("echo", json!({"dx": 10}), &[])
        .expect("the stepper is not fenced");
    assert_eq!(result.message["body"]["position"], 12);
}

#[test]
fn a_recovery_with_the_same_session_identifier_fences_the_old_opening() {
    // On a byte stream, each connection has its own owner: a new opening, which takes the ticks.
    const SESSION: &str = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b";
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = lose_a_step(&lockstep, Some(SESSION));
    let (held, mut old) = take_the_old_connection(&mut stepper, &lockstep);
    let fresh = held_session(&lockstep, true).with_session(SESSION);
    assert_eq!(stepper.recover(fresh).expect("recover"), Executed::No);
    let (outcome, code, _) = answer(&old.handle(held[0].clone()).expect("a response"));
    assert_eq!(
        (outcome.as_str(), code.as_str()),
        ("declined", "body_invalid")
    );
    assert_eq!(lockstep.clock().tick, 1);
    let result = stepper
        .step("echo", json!({"dx": 10}), &[])
        .expect("the new opening steps");
    assert_eq!(result.message["body"]["position"], 12);
}

/// A channel to an owner that other channels share, as a Zenoh server keeps one owner for each
/// session identifier.
struct Joint<H: Handler> {
    owner: Arc<Mutex<Owner<H>>>,
    inbox: VecDeque<Vec<u8>>,
    held: Vec<Vec<u8>>,
    broken: bool,
}

impl<H: Handler> Channel for Joint<H> {
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
            .lock()
            .expect("owner")
            .handle(frame_bytes.to_vec())
            .map_err(std::io::Error::other)?;
        self.inbox.push_back(response.to_vec());
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

type JointOwner = Arc<Mutex<Owner<Lockstep<World>>>>;

fn joint_owner(lockstep: &Lockstep<World>) -> JointOwner {
    Arc::new(Mutex::new(
        Owner::new(contract(), lockstep.share()).with_observer(quiet()),
    ))
}

fn joint_session(owner: &JointOwner, session: &str) -> Client<Joint<Lockstep<World>>> {
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    Client::new(
        Joint {
            owner: owner.clone(),
            inbox: VecDeque::new(),
            held: Vec::new(),
            broken: false,
        },
        &contract(),
    )
    .with_features(features)
    .with_session(session)
    .with_observer(quiet())
}

#[test]
fn a_recovery_that_reaches_the_old_opening_gives_no_verdict() {
    // Where one owner holds a session identifier, as a Zenoh server does, the same open reaches
    // the old opening again: it is stale there, so the recovery gives no verdict, and the delayed
    // step can still run. A new session identifier then finds that it ran.
    const SESSION: &str = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b";
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let owner = joint_owner(&lockstep);
    let mut stepper = LockstepClient::new(joint_session(&owner, SESSION)).expect("lockstep");
    stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    stepper.client().channel_mut().broken = true;
    let error = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    assert_eq!(error.executed(), Executed::Unknown);
    let held = std::mem::take(&mut stepper.client().channel_mut().held);
    let refused = stepper.recover(joint_session(&owner, SESSION));
    assert!(
        matches!(&refused, Err(Error::Rejected { code, .. }) if code == "seq_stale"),
        "{refused:?}"
    );
    assert!(stepper.uncertain.is_some());
    let response = owner
        .lock()
        .expect("owner")
        .handle(held[0].clone())
        .expect("a response");
    assert_eq!(answer(&response).0, "ok");
    let fresh = joint_owner(&lockstep);
    let other = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1c";
    assert_eq!(
        stepper
            .recover(joint_session(&fresh, other))
            .expect("recover"),
        Executed::Yes
    );
    assert_eq!((stepper.tick, stepper.state.as_deref()), (2, Some("p3")));
}

#[test]
fn a_recovery_reads_its_verdict_from_the_take() {
    // The report of an open can be older than the clock: the standby client opened before the
    // steps. Its take decides, and its opening then holds the ticks.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut standby = held_session(&lockstep, true);
    standby.open().expect("open");
    assert_eq!(standby.enabled()[ncp::lockstep::FEATURE]["tick"], 0);
    let nonce = standby.nonce().map(str::to_owned);
    let mut stepper = lose_a_step(&lockstep, None);
    let (held, mut old) = take_the_old_connection(&mut stepper, &lockstep);
    assert_eq!(stepper.recover(standby).expect("recover"), Executed::No);
    assert_eq!(lockstep.clock().holder, nonce);
    let (outcome, _, _) = answer(&old.handle(held[0].clone()).expect("a response"));
    assert_eq!(outcome, "declined");
    assert_eq!(lockstep.clock().tick, 1);
}

#[test]
fn a_delayed_take_of_an_abandoned_opening_is_declined() {
    // Profile rule 5.2: the term moved, so a late take cannot take the ticks from a newer holder.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut abandoned = held_session(&lockstep, true);
    abandoned.open().expect("open");
    abandoned.channel_mut().broken = true;
    let error = abandoned
        .call(ncp::lockstep::TAKE, json!({"term": 0}), &[])
        .expect_err("the connection broke");
    assert_eq!(error.executed(), Executed::Unknown);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    let late = abandoned.channel_mut().held[0].clone();
    let response = abandoned
        .channel_mut()
        .owner
        .handle(late)
        .expect("a response");
    let message = frame::decode(response.to_vec(), MAX_BOUND)
        .expect("the response")
        .message;
    assert_eq!(message["outcome"], "declined");
    assert_eq!(message["code"], "body_invalid");
    assert_eq!(message["body"][ncp::lockstep::FEATURE], json!({"term": 1}));
    let nonce = stepper.client().nonce().map(str::to_owned);
    assert_eq!(lockstep.clock().holder, nonce);
    let result = stepper.step("echo", json!({"dx": 1}), &[]).expect("step");
    assert_eq!(result.message["body"]["position"], 1);
}

#[test]
fn a_take_whose_term_moved_is_sent_again() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut late = held_session(&lockstep, true);
    late.open().expect("open"); // its report names term 0
    let mut other = LockstepClient::new(held_session(&lockstep, true)).expect("other"); // term 1
    let mut stepper = LockstepClient::new(late).expect("declined once, then it takes"); // term 2
    let nonce = stepper.client().nonce().map(str::to_owned);
    let clock = lockstep.clock();
    assert_eq!((clock.term, clock.holder), (2, nonce));
    stepper.step("echo", json!({"dx": 1}), &[]).expect("step");
    let fenced = other.step("echo", json!({"dx": 1}), &[]);
    assert!(matches!(&fenced, Err(Error::Declined { .. })), "{fenced:?}");
}

#[test]
fn a_take_needs_its_body_and_the_profile_defines_no_other_operation() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut client = held_session(&lockstep, true);
    client.open().expect("open");
    for (op, body) in [
        (ncp::lockstep::TAKE, json!({})),
        (ncp::lockstep::TAKE, json!({"term": "0"})),
        ("ncp.lockstep.other", json!({})),
    ] {
        let refused = client.call(op, body, &[]);
        assert!(
            matches!(&refused, Err(Error::Declined { code, .. }) if code == "body_invalid"),
            "{op}: {refused:?}"
        );
    }
    let clock = lockstep.clock();
    assert_eq!((clock.holder, clock.term, clock.tick), (None, 0, 0));
}

#[test]
fn a_restart_to_the_same_tick_with_another_state_gives_no_verdict() {
    // Profile rule 6.5: "did not run" needs exactly the clock that the client knew.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = lose_a_step(&lockstep, None); // it knows tick 1 and p2; tick 2 is uncertain
    let restarted = Lockstep::restored(
        World { position: 500 },
        &["echo"],
        1,
        Some("p500".into()),
        Some("e".repeat(64)),
        0,
    )
    .expect("restored");
    let verdict = stepper
        .recover(held_session(&restarted, true))
        .expect("recover");
    assert_eq!(verdict, Executed::Unknown);
    // Without a verdict, the client goes on from the owner's clock in the new session.
    assert_eq!(
        (
            stepper.tick,
            stepper.state.as_deref(),
            stepper.uncertain.clone()
        ),
        (1, Some("p500"), None)
    );
    let result = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect("the client holds the ticks");
    assert_eq!(result.message["body"]["position"], 501);
}

#[test]
fn profile_members_that_cannot_be_encoded_leave_the_detail() {
    // The owner keeps the decline and drops members that it cannot send.
    struct Refusing(usize);
    impl Handler for Refusing {
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            let mut members = Map::new();
            members.insert("ncp.big".into(), json!("x".repeat(self.0)));
            Err(ncp::declined_with("no", members))
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
    }
    // Too large for any frame; and larger than the session's bound, set to the smallest bound.
    for (size, bound) in [(2_000_000, MAX_BOUND), (100_000, HANDSHAKE_BOUND)] {
        let mut client = memory_of(
            Owner::new(contract(), Refusing(size)).with_observer(quiet()),
            false,
            0,
        )
        .with_bound(bound);
        client.open().expect("open");
        match client.call("echo", json!({}), &[]) {
            Err(Error::Declined { code, body, .. }) => {
                assert_eq!(
                    (code.as_str(), body),
                    ("body_invalid", json!({"detail": "no"}))
                );
            }
            other => panic!("expected declined, got {other:?}"),
        }
        client.ping().expect("the session goes on");
    }
}

#[test]
fn features_that_cannot_be_sent_refuse_the_open() {
    // Rule 7.1.3: the client reads the open response with the handshake bound.
    struct Generous(Arc<Mutex<Vec<String>>>);
    impl Handler for Generous {
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            let mut granted = Map::new();
            granted.insert("big".into(), json!({"blob": "x".repeat(70_000)}));
            Ok(granted)
        }
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
        fn close(&mut self, reason: &str) {
            self.0.lock().expect("lock").push(reason.to_owned());
        }
    }
    let closed = Arc::new(Mutex::new(Vec::new()));
    let mut features = Map::new();
    features.insert("big".into(), json!({}));
    let generous = Generous(closed.clone());
    let mut client = memory_of(
        Owner::new(contract(), generous).with_observer(quiet()),
        false,
        0,
    )
    .with_features(features);
    match client.open() {
        Err(Error::Rejected { code, .. }) => assert_eq!(code, "refused"),
        other => panic!("expected a rejection, got {other:?}"),
    }
    assert_eq!(*closed.lock().expect("lock"), vec!["refused".to_owned()]);
}

#[test]
fn a_rejected_open_takes_nothing() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    struct Full(Lockstep<World>);
    impl Handler for Full {
        fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            let _ = self.0.open(info);
            Err(Refused::new(
                "the owner serves its largest number of sessions",
            ))
        }
        fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
            self.0.validate(request)
        }
        fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
            self.0.execute(request)
        }
    }
    let mut refused = memory_of(
        Owner::new(contract(), Full(lockstep.share())).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    let rejected = refused.open();
    assert!(
        matches!(&rejected, Err(Error::Rejected { .. })),
        "{rejected:?}"
    );
    let nonce = stepper.client().nonce().map(str::to_owned);
    assert_eq!(lockstep.clock().holder, nonce);
    let result = stepper.step("echo", json!({"dx": 1}), &[]).expect("step");
    assert_eq!(result.message["body"]["position"], 1);
}

#[test]
fn no_step_follows_the_largest_tick() {
    // Profile rule 5.4: the tick stays an integer that a JSON number carries exactly.
    let max = ncp::lockstep::MAX_TICK;
    let lockstep = Lockstep::restored(
        World { position: 0 },
        &["echo"],
        max,
        Some("p0".into()),
        None,
        0,
    )
    .expect("restored");
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    let refused = stepper.step("echo", json!({"dx": 1}), &[]);
    assert!(matches!(&refused, Err(Error::Usage(_))), "{refused:?}");
    // The owner declines a step with any tick.
    let refused = stepper.client().call(
        "echo",
        json!({"dx": 1, "ncp.tick": {"tick": max, "state": "p0"}}),
        &[],
    );
    assert!(
        matches!(&refused, Err(Error::Declined { detail, .. })
            if detail.starts_with("tick:") && detail.contains("largest")),
        "{refused:?}"
    );
    assert_eq!(lockstep.clock().tick, max);
    assert!(Lockstep::restored(World { position: 0 }, &["echo"], max + 1, None, None, 0).is_err());
}

#[test]
fn an_owner_without_a_term_ends_the_session() {
    // Profile rule 3.4: parameters without a term come from an earlier revision of the profile.
    struct Earlier;
    impl Handler for Earlier {
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            let mut granted = Map::new();
            granted.insert(
                ncp::lockstep::FEATURE.into(),
                json!({"tick": 0, "state": null, "request": null}),
            );
            Ok(granted)
        }
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
    }
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let mut client = memory_of(
        Owner::new(contract(), Earlier).with_observer(quiet()),
        false,
        0,
    )
    .with_features(features);
    client.open().expect("open");
    let taken = ncp::lockstep::take(&mut client, None);
    assert!(matches!(taken, Err(Error::Usage(_))), "{taken:?}");
    assert!(client.ended());
}

#[test]
fn no_take_raises_the_largest_term() {
    // Profile rule 5.2: the term stays an integer that a JSON number carries exactly.
    let max = ncp::lockstep::MAX_TERM;
    let lockstep =
        Lockstep::restored(World { position: 0 }, &["echo"], 0, None, None, max).expect("restored");
    let mut client = held_session(&lockstep, true);
    client.open().expect("open");
    match ncp::lockstep::take(&mut client, None) {
        Err(Error::Declined { detail, body, .. }) => {
            assert_eq!(
                detail,
                "term: the term is the largest; no take can follow it"
            );
            // No other take ran, so the response names no term (rule 6.2).
            assert!(body.get(ncp::lockstep::FEATURE).is_none(), "{body}");
        }
        other => panic!("expected declined, got {other:?}"),
    }
    let clock = lockstep.clock();
    assert_eq!((clock.term, clock.holder), (max, None));
    assert!(Lockstep::restored(World { position: 0 }, &["echo"], 0, None, None, max + 1).is_err());
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
fn a_closed_request_schema_admits_the_tick() {
    // Section 11.1: additionalProperties does not apply to members whose names start with "ncp.",
    // and the take is a feature operation, to which the contract does not apply.
    let closed = Contract::from_bytes(
        br#"{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{"ncp.schema":{"request":{"type":"object","required":["dx"],"properties":{"dx":{"type":"integer"}},"additionalProperties":false},"result":{"type":"object","properties":{"position":{"type":"integer"}},"additionalProperties":false}}}},"streams":{}}"#.to_vec(),
    )
    .expect("contract");
    let lockstep = Lockstep::new(World { position: 0 }, &["step"]);
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let client = Client::new(
        Memory {
            owner: Owner::new(closed.clone(), lockstep.share()).with_observer(quiet()),
            inbox: VecDeque::new(),
            drop_responses: 0,
            lossy: false,
        },
        &closed,
    )
    .with_features(features)
    .with_observer(quiet());
    let mut stepper = LockstepClient::new(client).expect("lockstep");
    let result = stepper
        .step("step", json!({"dx": 2}), &[])
        .expect("the closed schema admits ncp.tick");
    assert_eq!(result.message["body"]["position"], 2);
    assert_eq!(closed.check_result("step", &result.message["body"]), None);
    assert_eq!(stepper.tick, 1);
    // Other members stay closed out.
    let refused = stepper.step("step", json!({"dx": 1, "dy": 1}), &[]);
    assert!(
        matches!(&refused, Err(Error::Declined { code, detail, .. })
            if code == "body_invalid" && detail.contains("\"dy\" is not allowed")),
        "{refused:?}"
    );
    assert_eq!(lockstep.clock().tick, 1);
}

#[test]
fn a_recovery_that_finds_the_step_of_another_session_gives_no_verdict() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut first = LockstepClient::new(held_session(&lockstep, true)).expect("first");
    first.client().channel_mut().broken = true;
    first
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    // Another client takes the ticks and makes the step with the same tick.
    let mut second = LockstepClient::new(held_session(&lockstep, true)).expect("second");
    second
        .step("echo", json!({"dx": 5}), &[])
        .expect("the other step");
    let verdict = first
        .recover(held_session(&lockstep, true))
        .expect("recover");
    assert_eq!(verdict, Executed::Unknown);
    assert_eq!(
        (first.tick, first.state.as_deref(), first.uncertain.clone()),
        (1, Some("p5"), None)
    );
    let result = first
        .step("echo", json!({"dx": 1}), &[])
        .expect("it holds the ticks now");
    assert_eq!(result.message["body"]["position"], 6);
}

/// A lockstep owner that changes its results, as an owner that breaks the profile can.
struct Altered {
    inner: Lockstep<World>,
    alter: fn(&str, &mut Value),
}

impl Handler for Altered {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        self.inner.open(info)
    }
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        self.inner.validate(request)
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        let mut reply = self.inner.execute(request)?;
        (self.alter)(request.op, &mut reply.body);
        Ok(reply)
    }
}

fn lockstep_features() -> Map<String, Value> {
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    features
}

#[test]
fn a_take_names_the_last_term_that_the_owner_told() {
    // Profile rule 4.1: after a declined step names the term, a take in the same session names it.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep"); // term 1
    let mut other = LockstepClient::new(held_session(&lockstep, true)).expect("other"); // term 2
    match stepper.step("echo", json!({"dx": 1}), &[]) {
        Err(Error::Declined { body, .. }) => {
            assert_eq!(body[ncp::lockstep::FEATURE], json!({"term": 2}));
        }
        unexpected => panic!("expected declined, got {unexpected:?}"),
    }
    assert_eq!(stepper.term, 2);
    let sent = stepper.client().channel_mut().frames.len();
    stepper.take().expect("take");
    assert_eq!(stepper.client().channel_mut().frames.len(), sent + 1); // one take, which ran
    let nonce = stepper.client().nonce().map(str::to_owned);
    let clock = lockstep.clock();
    assert_eq!((stepper.term, clock.term, clock.holder), (3, 3, nonce));
    let result = stepper.step("echo", json!({"dx": 1}), &[]).expect("step");
    assert_eq!(result.message["body"]["position"], 1);
    let fenced = other.step("echo", json!({"dx": 1}), &[]);
    assert!(matches!(&fenced, Err(Error::Declined { .. })), "{fenced:?}");
}

#[test]
fn the_client_checks_the_term_of_the_take() {
    // Profile rule 6.1: the body of the take names the term of the request plus 1.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let skipping = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == ncp::lockstep::TAKE {
                body["term"] = json!(body["term"].as_u64().unwrap_or_default() + 1);
            }
        },
    };
    let mut client = memory_of(
        Owner::new(contract(), skipping).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    client.open().expect("open");
    match ncp::lockstep::take(&mut client, None) {
        Err(Error::Ended { code, executed, .. }) => {
            assert_eq!((code.as_str(), executed), ("local.protocol", Executed::Yes));
        }
        unexpected => panic!("expected an ending, got {unexpected:?}"),
    }
    assert!(client.ended());
}

#[test]
fn the_client_checks_the_tick_and_the_request_of_a_step() {
    // Profile rule 6.3: ncp.tick in the result names the tick and the identity of the request.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let misnaming = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == "echo" {
                body[ncp::lockstep::TICK]["request"] = json!("0".repeat(64));
            }
        },
    };
    let client = memory_of(
        Owner::new(contract(), misnaming).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    let mut stepper = LockstepClient::new(client).expect("lockstep");
    match stepper.step("echo", json!({"dx": 2}), &[]) {
        Err(Error::Ended { code, executed, .. }) => {
            assert_eq!((code.as_str(), executed), ("local.protocol", Executed::Yes));
        }
        unexpected => panic!("expected an ending, got {unexpected:?}"),
    }
    assert_eq!(
        (stepper.tick, stepper.state.clone(), lockstep.clock().tick),
        (1, None, 1)
    );
    assert!(stepper.client().ended());
}

#[test]
fn a_client_stops_after_three_takes_whose_term_moved() {
    // Profile rule 6.2: a client stops after TAKE_ATTEMPTS takes without an ok response.
    struct Moving {
        term: u64,
        takes: Arc<AtomicUsize>,
    }
    impl Handler for Moving {
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            let mut granted = Map::new();
            granted.insert(
                ncp::lockstep::FEATURE.into(),
                json!({"tick": 0, "state": null, "request": null, "term": self.term}),
            );
            Ok(granted)
        }
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            self.takes.fetch_add(1, Ordering::SeqCst);
            self.term += 1; // another client takes the ticks each time
            let mut members = Map::new();
            members.insert(ncp::lockstep::FEATURE.into(), json!({"term": self.term}));
            Err(ncp::declined_with(
                format!("term: the term is {}", self.term),
                members,
            ))
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
    }
    let takes = Arc::new(AtomicUsize::new(0));
    let moving = Moving {
        term: 0,
        takes: takes.clone(),
    };
    let mut client = memory_of(
        Owner::new(contract(), moving).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    client.open().expect("open");
    match ncp::lockstep::take(&mut client, None) {
        Err(Error::Declined { body, .. }) => {
            assert_eq!(body[ncp::lockstep::FEATURE], json!({"term": 3}));
        }
        unexpected => panic!("expected declined, got {unexpected:?}"),
    }
    assert_eq!(takes.load(Ordering::SeqCst), ncp::lockstep::TAKE_ATTEMPTS);
    client.ping().expect("the session goes on");
}

/// A client of `handler` over a channel that holds back requests once it breaks, with the feature.
fn held_with<H: Handler>(handler: H) -> Client<Held<H>> {
    Client::new(
        Held {
            owner: Owner::new(contract(), handler),
            inbox: VecDeque::new(),
            held: Vec::new(),
            frames: Vec::new(),
            broken: false,
        },
        &contract(),
    )
    .with_features(lockstep_features())
    .with_observer(quiet())
}

/// A lockstep owner where another opening takes the ticks just before each take, while
/// `contest` is set.
struct Contested {
    inner: Lockstep<World>,
    contest: Arc<std::sync::atomic::AtomicBool>,
}

impl Handler for Contested {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        self.inner.open(info)
    }
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if self.contest.load(Ordering::SeqCst) && request.op == ncp::lockstep::TAKE {
            let body = json!({"term": self.inner.clock().term});
            let identity = "0".repeat(64);
            let nonce = "f".repeat(32);
            let other = Request {
                body: &body,
                identity: &identity,
                nonce: &nonce,
                ..*request
            };
            self.inner.validate(&other)?;
            self.inner.execute(&other).map_err(Invalid::Failed)?;
        }
        self.inner.validate(request)
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        self.inner.execute(request)
    }
}

#[test]
fn a_take_that_fails_keeps_the_term_that_the_owner_told() {
    // Profile rule 4.1: the next take names the term of the last decline.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let contest = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let contested = Contested {
        inner: lockstep.share(),
        contest: contest.clone(),
    };
    let mut stepper = LockstepClient::new(held_with(contested)).expect("lockstep"); // term 1
    contest.store(true, Ordering::SeqCst);
    match stepper.take() {
        Err(Error::Declined { body, .. }) => {
            assert_eq!(body[ncp::lockstep::FEATURE], json!({"term": 4}));
        }
        unexpected => panic!("expected declined, got {unexpected:?}"),
    }
    assert_eq!(stepper.term, 4);
    contest.store(false, Ordering::SeqCst);
    let sent = stepper.client().channel_mut().frames.len();
    stepper.take().expect("take");
    assert_eq!(stepper.client().channel_mut().frames.len(), sent + 1); // one take, with term 4
    assert_eq!((stepper.term, lockstep.clock().term), (5, 5));
}

#[test]
fn a_recovery_whose_take_is_declined_keeps_the_step_uncertain() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let contest = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let contested = |contest: &Arc<std::sync::atomic::AtomicBool>| Contested {
        inner: lockstep.share(),
        contest: contest.clone(),
    };
    let mut stepper = LockstepClient::new(held_with(contested(&contest))).expect("lockstep");
    stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    stepper.client().channel_mut().broken = true;
    let error = stepper
        .step("echo", json!({"dx": 1}), &[])
        .expect_err("the connection broke");
    assert_eq!(error.executed(), Executed::Unknown);
    contest.store(true, Ordering::SeqCst);
    let refused = stepper.recover(held_with(contested(&contest)));
    assert!(
        matches!(&refused, Err(Error::Declined { .. })),
        "{refused:?}"
    );
    assert!(stepper.uncertain.is_some()); // still possibly executed
    contest.store(false, Ordering::SeqCst);
    // The other opening's takes moved only the term, and the lost step never arrived: the clock is
    // the one that the client knew, so the step did not run.
    let verdict = stepper
        .recover(held_with(contested(&contest)))
        .expect("recover");
    assert_eq!(verdict, Executed::No);
}

#[test]
fn a_response_without_a_member_of_the_clock_ends_the_session() {
    // Profile rules 5.3 and 6.1: the take's body has all four members; rule 6.3: ncp.tick has all
    // three.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let lacking_take = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == ncp::lockstep::TAKE {
                if let Some(object) = body.as_object_mut() {
                    object.remove("state");
                }
            }
        },
    };
    let mut client = memory_of(
        Owner::new(contract(), lacking_take).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    client.open().expect("open");
    match ncp::lockstep::take(&mut client, None) {
        Err(Error::Ended { code, executed, .. }) => {
            assert_eq!((code.as_str(), executed), ("local.protocol", Executed::Yes));
        }
        unexpected => panic!("expected an ending, got {unexpected:?}"),
    }
    assert!(client.ended());
    let lacking_step = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == "echo" {
                if let Some(object) = body[ncp::lockstep::TICK].as_object_mut() {
                    object.remove("state");
                }
            }
        },
    };
    let client = memory_of(
        Owner::new(contract(), lacking_step).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    let mut stepper = LockstepClient::new(client).expect("lockstep");
    match stepper.step("echo", json!({"dx": 2}), &[]) {
        Err(Error::Ended { code, executed, .. }) => {
            assert_eq!((code.as_str(), executed), ("local.protocol", Executed::Yes));
        }
        unexpected => panic!("expected an ending, got {unexpected:?}"),
    }
    assert_eq!((stepper.tick, lockstep.clock().tick), (1, 1));
    assert!(stepper.client().ended());
}

#[test]
fn other_operations_change_neither_the_clock_nor_the_holder() {
    // Profile rule 5.6.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut stepper = LockstepClient::new(held_session(&lockstep, true)).expect("lockstep");
    stepper.step("echo", json!({"dx": 2}), &[]).expect("step");
    let before = lockstep.clock();
    let result = stepper
        .client()
        .call("big", json!({}), &[])
        .expect("another operation");
    assert_eq!(result.message["body"]["position"], 2);
    let after = lockstep.clock();
    assert_eq!(
        (
            after.tick,
            after.state,
            after.request,
            after.term,
            after.holder
        ),
        (
            before.tick,
            before.state,
            before.request,
            before.term,
            before.holder
        )
    );
}

#[test]
fn a_client_acts_on_the_member_and_not_on_the_detail() {
    // Profile rule 5.8: the detail says 99, the member says 5; the client names 5.
    struct Misleading(Arc<Mutex<Vec<u64>>>);
    impl Handler for Misleading {
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            let mut granted = Map::new();
            granted.insert(
                ncp::lockstep::FEATURE.into(),
                json!({"tick": 0, "state": null, "request": null, "term": 0}),
            );
            Ok(granted)
        }
        fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
            let term = request.body["term"].as_u64().unwrap_or(u64::MAX);
            self.0.lock().expect("lock").push(term);
            if term == 5 {
                return Ok(());
            }
            let mut members = Map::new();
            members.insert(ncp::lockstep::FEATURE.into(), json!({"term": 5}));
            Err(ncp::declined_with("term: the term is 99", members))
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({"tick": 0, "state": null, "request": null, "term": 6}).into())
        }
    }
    let named = Arc::new(Mutex::new(Vec::new()));
    let mut client = memory_of(
        Owner::new(contract(), Misleading(named.clone())).with_observer(quiet()),
        false,
        0,
    )
    .with_features(lockstep_features());
    client.open().expect("open");
    let taken = ncp::lockstep::take(&mut client, None).expect("take");
    assert_eq!(taken, ((0, None, None), 6));
    assert_eq!(*named.lock().expect("lock"), vec![0, 5]);
}

#[test]
fn an_owner_ignores_the_members_of_the_feature_parameters() {
    // Profile rule 3.1.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let mut features = Map::new();
    features.insert(
        ncp::lockstep::FEATURE.into(),
        json!({"tick": 99, "other": true}),
    );
    let mut client = held_session(&lockstep, true).with_features(features);
    client.open().expect("open");
    assert_eq!(
        client.enabled()[ncp::lockstep::FEATURE],
        json!({"tick": 0, "state": "p0", "request": null, "term": 0})
    );
    let mut stepper = LockstepClient::new(client).expect("lockstep");
    let result = stepper.step("echo", json!({"dx": 1}), &[]).expect("step");
    assert_eq!(result.message["body"]["position"], 1);
}

#[should_panic(expected = "state digest")]
#[test]
fn an_application_digest_of_the_wrong_length_is_refused() {
    // Terms: a state digest has 1 to 128 characters; a wrong one is refused at the start.
    struct Wordy;
    impl Handler for Wordy {
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Ok(json!({}).into())
        }
    }
    impl Stepper for Wordy {
        fn state(&self) -> Option<String> {
            Some("x".repeat(200))
        }
    }
    let _ = Lockstep::new(Wordy, &["echo"]);
}

#[test]
fn the_verdict_of_a_recovery() {
    use ncp::lockstep::judge;
    let at = |tick: u64, state: &str, request: &str| {
        (tick, Some(state.to_owned()), Some(request.to_owned()))
    };
    let known = at(4, "s4", "r4");
    let step = (5, Some("r5".to_owned()));
    assert_eq!(judge(&known, &step, &at(5, "s5", "r5")), Executed::Yes);
    assert_eq!(judge(&known, &step, &known), Executed::No);
    for taken in [
        at(5, "s5", "other"),
        at(4, "s4", "other"),
        at(4, "other", "r4"),
        at(3, "s3", "r3"),
        at(6, "s6", "r6"),
    ] {
        assert_eq!(judge(&known, &step, &taken), Executed::Unknown, "{taken:?}");
    }
    // Without the identity of its request, "ran" cannot be shown.
    assert_eq!(
        judge(&known, &(5, None), &(5, Some("s5".into()), None)),
        Executed::Unknown
    );
}

/// A request as the owner hands it to a handler.
fn handler_request<'a>(
    op: &'a str,
    body: &'a Value,
    nonce: &'a str,
    identity: &'a str,
    contract: &'a Contract,
    features: &'a Map<String, Value>,
    decoded: &'a frame::Decoded,
) -> Request<'a> {
    Request {
        op,
        body,
        seq: 1,
        session: "s",
        identity,
        contract,
        run: None,
        features,
        nonce,
        decoded,
    }
}

fn empty_decoded(identity: &str) -> frame::Decoded {
    frame::Decoded {
        message: json!({}),
        arrays: Vec::new(),
        identity: identity.into(),
        frame: Arc::new(Vec::new()),
    }
}

#[test]
fn a_take_waits_for_a_checked_step_and_an_open_does_not() {
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let contract = contract();
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let decoded = empty_decoded("r1");
    let mut first = lockstep.share();
    let take_body = json!({"term": 0});
    let take = handler_request(
        ncp::lockstep::TAKE,
        &take_body,
        "n1",
        "t1",
        &contract,
        &features,
        &decoded,
    );
    first.validate(&take).expect("the take is checked");
    first.execute(&take).expect("the take runs");
    let step_body = json!({"dx": 3, "ncp.tick": {"tick": 1, "state": "p0"}});
    let step = handler_request(
        "echo", &step_body, "n1", "r1", &contract, &features, &decoded,
    );
    first.validate(&step).expect("the step is checked");
    // An open only reports: it does not wait for the checked step, and sees the clock before it.
    let mut reader = lockstep.share();
    let report = reader
        .open(&OpenInfo {
            session: "s",
            contract: &contract,
            run: None,
            features: &features,
            nonce: "n3",
        })
        .expect("open")[ncp::lockstep::FEATURE]
        .clone();
    assert_eq!(
        report,
        json!({"tick": 0, "state": "p0", "request": null, "term": 1})
    );
    // A take of another opening waits until the checked step has run.
    let mut second = lockstep.share();
    let waiting = std::thread::spawn(move || {
        let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
        let mut features = Map::new();
        features.insert(ncp::lockstep::FEATURE.into(), json!({}));
        let decoded = empty_decoded("t2");
        let body = json!({"term": 1});
        let take = handler_request(
            ncp::lockstep::TAKE,
            &body,
            "n2",
            "t2",
            &contract,
            &features,
            &decoded,
        );
        second.validate(&take).expect("the take is checked");
        second.execute(&take).expect("the take runs").body
    });
    std::thread::sleep(Duration::from_millis(100));
    assert!(!waiting.is_finished(), "the take did not wait");
    first.execute(&step).expect("the step runs");
    assert_eq!(
        waiting.join().expect("the take"),
        json!({"tick": 1, "state": "p3", "request": "r1", "term": 2})
    );
    assert_eq!(lockstep.clock().holder.as_deref(), Some("n2"));
}

#[test]
fn a_step_waits_for_a_checked_take() {
    // Profile rule 5.1: the step of the holder waits while another opening's take is checked;
    // after the take, the holder check declines it, with the term.
    let lockstep = Lockstep::new(World { position: 0 }, &["echo"]);
    let contract = contract();
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let decoded = empty_decoded("t");
    let mut first = lockstep.share();
    let take_body = json!({"term": 0});
    let take = handler_request(
        ncp::lockstep::TAKE,
        &take_body,
        "n1",
        "t1",
        &contract,
        &features,
        &decoded,
    );
    first.validate(&take).expect("the take is checked");
    first.execute(&take).expect("the take runs");
    let mut second = lockstep.share();
    let other_body = json!({"term": 1});
    let other = handler_request(
        ncp::lockstep::TAKE,
        &other_body,
        "n2",
        "t2",
        &contract,
        &features,
        &decoded,
    );
    second.validate(&other).expect("the other take is checked");
    let mut stepper = lockstep.share();
    let waiting = std::thread::spawn(move || {
        let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
        let mut features = Map::new();
        features.insert(ncp::lockstep::FEATURE.into(), json!({}));
        let decoded = empty_decoded("r1");
        let body = json!({"dx": 1, "ncp.tick": {"tick": 1, "state": "p0"}});
        let step = handler_request("echo", &body, "n1", "r1", &contract, &features, &decoded);
        match stepper.validate(&step) {
            Err(Invalid::Declined(decline)) if !decline.members.is_empty() => {
                (decline.detail, decline.members)
            }
            other => panic!("expected a decline with members, got {other:?}"),
        }
    });
    std::thread::sleep(Duration::from_millis(100));
    assert!(!waiting.is_finished(), "the step did not wait");
    second.execute(&other).expect("the other take runs");
    let (detail, members) = waiting.join().expect("the step");
    assert!(detail.starts_with("holder:"), "{detail}");
    assert_eq!(members[ncp::lockstep::FEATURE], json!({"term": 2}));
    assert_eq!(lockstep.clock().tick, 0);
}
