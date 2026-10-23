//! Sessions end to end: in-memory and lossy channels, TCP, transcripts, streams, and the
//! Python reference owner when `python3` is available.

use ncp::exchange::Channel;
use ncp::frame::{self, Array, HANDSHAKE_BOUND, MAX_BOUND};
use ncp::{binding, transcript, Client, Contract, Decoded, Delivery, Error, Handler, Owner, Publisher, Reply, Subscriber};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"big":{}},"streams":{"sensor":{}}}"#;

fn contract() -> Contract {
    Contract::from_bytes(CONTRACT.to_vec()).expect("contract")
}

#[derive(Clone, Default)]
struct Echo {
    executed: Arc<AtomicUsize>,
}

impl Handler for Echo {
    fn validate(&mut self, _op: &str, request: &Decoded) -> Result<(), String> {
        if request.message["body"]["invalid"] == true {
            return Err("invalid requested".into());
        }
        Ok(())
    }
    fn execute(&mut self, op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        self.executed.fetch_add(1, Ordering::SeqCst);
        let body = &request.message["body"];
        match op {
            "fail" => Err("requested failure".into()),
            "big" => Ok(json!({"blob": "z".repeat(body["size"].as_u64().unwrap_or(0) as usize)}).into()),
            _ => Ok(Reply { body: body.clone(), arrays: request.owned_arrays() }),
        }
    }
}

fn owner(handler: Echo, max_bound: usize) -> Owner<Echo> {
    let contract = contract();
    Owner::new(&contract.application, &contract.identity, handler, contract.operations, max_bound)
}

/// A channel that hands frames straight to an owner. `drop_responses` loses the next responses
/// after the owner handled the request, as a lossy binding can.
struct Memory {
    owner: Owner<Echo>,
    inbox: VecDeque<Vec<u8>>,
    drop_responses: usize,
    lossy: bool,
}

impl Channel for Memory {
    fn lossy(&self) -> bool {
        self.lossy
    }
    fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
        let response = self.owner.handle(frame_bytes.to_vec()).map_err(std::io::Error::other)?;
        if self.drop_responses > 0 {
            self.drop_responses -= 1;
        } else {
            self.inbox.push_back(response.to_vec());
        }
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, Error> {
        self.inbox
            .pop_front()
            .ok_or_else(|| Error::Io(std::io::Error::new(std::io::ErrorKind::TimedOut, "no frame")))
    }
}

fn memory(handler: Echo, lossy: bool, drop_responses: usize) -> Client<Memory> {
    let contract = contract();
    let channel = Memory { owner: owner(handler, MAX_BOUND), inbox: VecDeque::new(), drop_responses, lossy };
    Client::new(channel, &contract.application, &contract.identity)
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
    Value::Array(arrays.iter().enumerate().map(|(i, a)| a.reference(i)).collect())
}

#[test]
fn memory_session_rules() {
    let echo = Echo::default();
    let mut client = memory(echo.clone(), false, 0);
    let opened = client.open().expect("open");
    assert_eq!(opened["bound"], MAX_BOUND.min(ncp::DEFAULT_BOUND));
    assert_eq!(opened["implementation"], ncp::IMPLEMENTATION);
    let reply = client.call("echo", json!({"x": 1.5, "s": "é😀"}), &[]).expect("call");
    assert_eq!(reply.message["body"], json!({"x": 1.5, "s": "é😀"}));
    match client.call("echo", json!({"invalid": true}), &[]) {
        Err(Error::Rejected { code, body }) => {
            assert_eq!(code, "body_invalid");
            assert_eq!(body["detail"], "invalid requested");
        }
        other => panic!("expected a rejection, got {other:?}"),
    }
    match client.call("missing", json!({}), &[]) {
        Err(Error::Rejected { code, .. }) => assert_eq!(code, "unknown_op"),
        other => panic!("expected unknown_op, got {other:?}"),
    }
    // A rejection changes nothing: the next call still uses the next sequence number.
    client.call("echo", json!({"after": "rejections"}), &[]).expect("call after rejections");
    assert_eq!(echo.executed.load(Ordering::SeqCst), 2);
    client.close().expect("close");
    assert!(matches!(client.call("echo", json!({}), &[]), Err(Error::Protocol(_))));
}

#[test]
fn arrays_of_every_dtype_round_trip() {
    let mut client = memory(Echo::default(), false, 0);
    client.open().expect("open");
    let arrays = all_dtypes();
    let reply = client.call("echo", json!({"v": array_body(&arrays)}), &arrays).expect("call");
    assert_eq!(reply.arrays.len(), arrays.len());
    for (index, array) in arrays.iter().enumerate() {
        assert_eq!(reply.array_bytes(index).expect("bytes"), &array.data[..], "array {index}");
        assert_eq!(reply.arrays[index].dtype, array.dtype);
    }
    assert_eq!(reply.array_f64(9).expect("f64")[3], std::f64::consts::PI);
    assert_eq!(reply.array_i64(7).expect("i64"), vec![i64::MIN, i64::MAX]);
}

#[test]
fn endings_report_whether_the_request_executed() {
    let mut client = memory(Echo::default(), false, 0);
    client.open().expect("open");
    match client.call("fail", json!({}), &[]) {
        Err(Error::Ended { code, executed }) => assert_eq!((code.as_str(), executed), ("owner_failure", "unknown")),
        other => panic!("expected owner_failure, got {other:?}"),
    }
    assert!(client.call("echo", json!({}), &[]).is_err());

    let mut client = memory(Echo::default(), false, 0).with_bound(HANDSHAKE_BOUND);
    client.open().expect("open");
    match client.call("big", json!({"size": HANDSHAKE_BOUND}), &[]) {
        Err(Error::Ended { code, executed }) => assert_eq!((code.as_str(), executed), ("result_too_large", "yes")),
        other => panic!("expected result_too_large, got {other:?}"),
    }
}

#[test]
fn a_lost_response_is_retried_and_executes_once() {
    let echo = Echo::default();
    let mut client = memory(echo.clone(), true, 0);
    client.open().expect("open");
    // Lose the next two responses: the client sends the same request three times.
    set_drops(&mut client, 2);
    let reply = client.call("echo", json!({"once": true}), &[]).expect("call with retries");
    assert_eq!(reply.message["body"], json!({"once": true}));
    assert_eq!(echo.executed.load(Ordering::SeqCst), 1, "a retried request must execute exactly once");
    set_drops(&mut client, 4);
    match client.call("echo", json!({}), &[]) {
        Err(Error::Ended { code, executed }) => assert_eq!((code.as_str(), executed), ("timeout", "unknown")),
        other => panic!("expected a timeout, got {other:?}"),
    }
}

fn set_drops(client: &mut Client<Memory>, drops: usize) {
    client.channel_mut().drop_responses = drops;
}

#[test]
fn tcp_session_with_transcripts() {
    let directory = scratch("tcp");
    let owner_tap = Arc::new(ncp::Tap::create(directory.join("owner.ncpt")).expect("tap"));
    let client_tap = Arc::new(ncp::Tap::create(directory.join("client.ncpt")).expect("tap"));
    let listener = binding::listen_tcp("127.0.0.1:0", false).expect("listen");
    let address = listener.local_addr().expect("address");
    let tap = owner_tap.clone();
    let server = std::thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        let mut channel = binding::tcp_channel(stream).expect("channel").with_tap(tap);
        let mut owner = owner(Echo::default(), MAX_BOUND);
        binding::serve(&mut owner, &mut channel).expect("serve");
        owner.closed()
    });
    let contract = contract();
    let channel = binding::connect_tcp(address, false).expect("connect").with_tap(client_tap.clone());
    let mut client = Client::new(channel, &contract.application, &contract.identity).with_run("tcp-test");
    client.open().expect("open");
    let arrays = all_dtypes();
    for step in 0..50 {
        let reply = client.call("echo", json!({"step": step, "v": array_body(&arrays)}), &arrays).expect("call");
        assert_eq!(reply.message["body"]["step"], step);
    }
    let _ = client.call("echo", json!({"invalid": true}), &[]);
    client.close().expect("close");
    assert!(server.join().expect("server thread"), "the owner saw close");
    owner_tap.flush().expect("flush");
    client_tap.flush().expect("flush");
    for (name, role) in [("owner.ncpt", "owner"), ("client.ncpt", "client")] {
        let sessions = transcript::verify(directory.join(name)).expect("verify");
        assert_eq!(sessions.len(), 1, "{name}");
        let report = sessions.values().next().expect("session");
        assert_eq!(report.role, role, "{name}");
        assert!(report.complete, "{name}: {report:?}");
        assert!(report.problems.is_empty(), "{name}: {:?}", report.problems);
        assert_eq!(report.requests, 53, "{name}: open, 50 calls, 1 rejected call, close");
    }
}

#[test]
fn transcripts_detect_tampering() {
    let directory = scratch("tamper");
    let path = directory.join("client.ncpt");
    {
        let tap = Arc::new(ncp::Tap::create(&path).expect("tap"));
        let contract = contract();
        let mut channel = Memory { owner: owner(Echo::default(), MAX_BOUND), inbox: VecDeque::new(), drop_responses: 0, lossy: false };
        let session = ncp::random_session();
        let mut ack = Value::Null;
        for (seq, op, body) in [(0, "open", json!({"application": "echo", "contract": contract.identity, "bound": HANDSHAKE_BOUND})),
                                (1, "echo", json!({"a": 1})), (2, "echo", json!({"a": 2}))] {
            let request = frame::encode(&json!({"ncp": 2, "session": session, "seq": seq, "op": op, "ack": ack, "body": body}), &[]).expect("encode");
            tap.record(transcript::SENT, &request);
            channel.send(&request).expect("send");
            let response = channel.receive(MAX_BOUND).expect("response");
            tap.record(transcript::RECEIVED, &response);
            ack = Value::from(frame::identity(&response));
        }
        // A forged request whose ack names no response the client received.
        let forged = frame::encode(&json!({"ncp": 2, "session": session, "seq": 3, "op": "echo", "ack": "0".repeat(64), "body": {}}), &[]).expect("encode");
        tap.record(transcript::SENT, &forged);
        tap.flush().expect("flush");
    }
    let sessions = transcript::verify(&path).expect("verify");
    let report = sessions.values().next().expect("session");
    assert!(!report.complete);
    assert!(report.problems.iter().any(|p| p.contains("ack does not name")), "{:?}", report.problems);
    assert!(report.problems.iter().any(|p| p.contains("no response")), "{:?}", report.problems);
}

#[test]
fn bad_frame_ends_a_tcp_connection() {
    let listener = binding::listen_tcp("127.0.0.1:0", false).expect("listen");
    let address = listener.local_addr().expect("address");
    let server = std::thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        let mut channel = binding::tcp_channel(stream).expect("channel");
        let mut owner = owner(Echo::default(), MAX_BOUND);
        binding::serve(&mut owner, &mut channel).expect("serve");
    });
    let mut channel = binding::connect_tcp(address, false).expect("connect");
    channel.send_frame(b"NCP\x01\x00\x00\x00\x08\x00\x00\x00\x00{}      ").expect("send junk");
    let response = channel.receive_frame(MAX_BOUND).expect("bad frame response");
    let message = frame::decode(response, MAX_BOUND).expect("decode").message;
    assert_eq!((message["outcome"].as_str(), message["code"].as_str()), (Some("ended"), Some("bad_frame")));
    assert!(message["session"].is_null() && message["request"].is_null());
    server.join().expect("server thread");
    assert!(channel.receive_frame(MAX_BOUND).is_err(), "the owner closed the connection");
}

#[test]
fn remote_addresses_need_permission() {
    let error = binding::connect_tcp("192.0.2.1:9", false).expect_err("refused");
    assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
    let error = binding::listen_tcp("0.0.0.0:0", false).expect_err("refused");
    assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
}

#[test]
fn many_sessions_with_call_all() {
    let contract = contract();
    let listener = binding::listen_tcp("127.0.0.1:0", false).expect("listen");
    let address = listener.local_addr().expect("address");
    let sessions = 16;
    let executed = Arc::new(Mutex::new(Vec::new()));
    let record = executed.clone();
    let server = std::thread::spawn(move || {
        let mut workers = Vec::new();
        for _ in 0..sessions {
            let (stream, _) = listener.accept().expect("accept");
            let record = record.clone();
            workers.push(std::thread::spawn(move || {
                let echo = Echo::default();
                let mut channel = binding::tcp_channel(stream).expect("channel");
                let mut owner = owner(echo.clone(), MAX_BOUND);
                binding::serve(&mut owner, &mut channel).expect("serve");
                record.lock().expect("lock").push(echo.executed.load(Ordering::SeqCst));
            }));
        }
        for worker in workers {
            worker.join().expect("worker");
        }
    });
    let mut clients: Vec<_> = (0..sessions)
        .map(|_| {
            let mut client = Client::new(binding::connect_tcp(address, false).expect("connect"), &contract.application, &contract.identity);
            client.open().expect("open");
            client
        })
        .collect();
    for round in 0..20 {
        let bodies = (0..sessions).map(|agent| json!({"agent": agent, "round": round})).collect();
        for (agent, result) in ncp::call_all(&mut clients, "echo", bodies).into_iter().enumerate() {
            assert_eq!(result.expect("call").message["body"], json!({"agent": agent, "round": round}));
        }
    }
    for client in &mut clients {
        client.close().expect("close");
    }
    server.join().expect("server");
    assert_eq!(*executed.lock().expect("lock"), vec![20; sessions]);
}

#[test]
fn streams_detect_loss_repeats_and_forgery() {
    let contract = contract();
    let mut publisher = Publisher::new("sensor/left", &contract.identity).expect("publisher");
    let frames: Vec<Vec<u8>> = (0..6)
        .map(|i| {
            let reading = Array::from_f32(&[i as f32]);
            publisher.publish(json!({"i": i, "reading": reading.reference(0)}), &[reading]).expect("publish")
        })
        .collect();
    let mut subscriber = Subscriber::new([contract.identity.clone()]);
    let mut receive = |bytes: &[u8]| subscriber.receive(bytes.to_vec()).0;
    assert_eq!(receive(&frames[0]), Delivery::Accepted { lost: 0 });
    assert_eq!(receive(&frames[0]), Delivery::Repeat);
    assert_eq!(receive(&frames[3]), Delivery::Accepted { lost: 2 });
    assert_eq!(receive(&frames[2]), Delivery::Repeat);
    assert_eq!(receive(&frames[4]), Delivery::Accepted { lost: 0 });
    let mut forger = Publisher::new("sensor/left", &contract.identity).expect("publisher");
    let forged: Vec<Vec<u8>> = (0..6).map(|i| forger.publish(json!({"forged": i}), &[]).expect("publish")).collect();
    assert_eq!(receive(&forged[5]), Delivery::BrokenChain);
    assert_eq!(receive(&frames[5]), Delivery::Accepted { lost: 0 });
    let mut damaged = frames[5].clone();
    damaged[20] ^= 1;
    assert_eq!(receive(&damaged), Delivery::BadFrame);
    let mut stranger = Publisher::new("other", &"0".repeat(64)).expect("publisher");
    assert_eq!(receive(&stranger.publish(json!({}), &[]).expect("publish")), Delivery::UnknownContract);
}

fn python_echo_owner() -> Option<std::process::Command> {
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python/tests/echo_owner.py");
    let available = std::process::Command::new("python3").arg("-c").arg("import sys; sys.exit(sys.version_info < (3, 10))").status().is_ok_and(|s| s.success());
    if !available {
        eprintln!("python3 >= 3.10 not found: skipping the cross-language test");
        return None;
    }
    let mut command = std::process::Command::new("python3");
    command.arg("-I").arg(script);
    Some(command)
}

#[test]
fn rust_client_with_the_python_owner() {
    let Some(command) = python_echo_owner() else { return };
    let (channel, mut child) = binding::spawn(command).expect("spawn");
    // The Python echo owner serves the contract of python/tests/echo_owner.py.
    let mut client = Client::new(channel, "echo", &python_contract_identity());
    let opened = client.open().expect("open");
    assert!(opened["implementation"].as_str().is_some_and(|s| s.starts_with("ncp-python/")));
    let arrays = all_dtypes();
    let reply = client.call("echo", json!({"v": array_body(&arrays), "text": "é😀", "n": 9007199254740991_i64}), &arrays).expect("call");
    assert_eq!(reply.message["body"]["text"], "é😀");
    assert_eq!(reply.message["body"]["n"], 9007199254740991_i64);
    for (index, array) in arrays.iter().enumerate() {
        assert_eq!(reply.array_bytes(index).expect("bytes"), &array.data[..], "array {index}");
    }
    match client.call("echo", json!({"invalid": true}), &[]) {
        Err(Error::Rejected { code, .. }) => assert_eq!(code, "body_invalid"),
        other => panic!("expected body_invalid, got {other:?}"),
    }
    client.close().expect("close");
    assert!(child.wait().expect("wait").success());
}

fn python_contract_identity() -> String {
    let output = std::process::Command::new("python3")
        .arg("-I")
        .arg("-c")
        .arg("import sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; from echo_owner import CONTRACT; print(CONTRACT.identity)")
        .arg(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python"))
        .arg(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python/tests"))
        .output()
        .expect("python3");
    String::from_utf8(output.stdout).expect("utf-8").trim().to_owned()
}

fn scratch(name: &str) -> PathBuf {
    let directory = std::env::temp_dir().join(format!("ncp-rust-tests-{}-{name}-{}", std::process::id(), ncp::random_session()));
    std::fs::create_dir_all(&directory).expect("scratch directory");
    directory
}

#[test]
fn encoders_refuse_frames_that_receivers_must_reject() {
    let ok = Array::from_u32(&[1, 2, 3]);
    assert!(frame::encode(&json!({"n": 9007199254740991_u64, "m": -9007199254740991_i64}), &[]).is_ok());
    assert!(frame::encode(&json!({"n": 9007199254740992_u64}), &[]).is_err(), "integer above 2^53 - 1");
    assert!(frame::encode(&json!({"n": i64::MIN}), &[]).is_err(), "integer below -(2^53 - 1)");
    let mut deep = json!(1);
    for _ in 0..63 {
        deep = json!([deep]);
    }
    assert!(frame::encode(&json!({"d": deep.clone()}), &[]).is_ok(), "64 levels, a number at the deepest level");
    assert!(frame::encode(&json!({"d": [deep]}), &[]).is_err(), "65 levels");
    let x = Array::from_u8(b"x");
    let mut nested = x.reference(0);
    for _ in 0..60 {
        nested = json!([nested]);
    }
    assert!(frame::encode(&json!({"a": nested}), std::slice::from_ref(&x)).is_ok(), "array shape list at level 64");
    assert!(frame::encode(&json!({"a": [nested]}), std::slice::from_ref(&x)).is_err(), "array shape list at level 65");
    assert!(frame::encode(&json!({"a": 1}), std::slice::from_ref(&ok)).is_err(), "unreferenced array");
    assert!(frame::encode(&json!({"a": ok.reference(0), "b": ok.reference(0)}), std::slice::from_ref(&ok)).is_err(), "array referred to twice");
    assert!(frame::encode(&json!({"a": ok.reference(1)}), std::slice::from_ref(&ok)).is_err(), "reference index out of range");
    let mut wrong_shape = ok.reference(0);
    wrong_shape["ncp.array"]["shape"] = json!([4]);
    assert!(frame::encode(&json!({"a": wrong_shape}), std::slice::from_ref(&ok)).is_err(), "reference shape differs");
    let inconsistent = Array { dtype: ok.dtype, shape: vec![2], data: ok.data.clone() };
    assert!(frame::encode(&json!({"a": inconsistent.reference(0)}), &[inconsistent]).is_err(), "array shape differs from its data");
    assert!(frame::encode(&json!({"a": ok.reference(0)}), &[ok]).is_ok());
}

#[derive(Clone, Default)]
struct BadResult;

impl Handler for BadResult {
    fn validate(&mut self, _op: &str, _request: &Decoded) -> Result<(), String> {
        Ok(())
    }
    fn execute(&mut self, _op: &str, _request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        Ok(json!({"too_big": u64::MAX}).into())
    }
}

#[test]
fn an_unencodable_result_ends_the_session_with_owner_failure() {
    let contract = contract();
    let mut owner = Owner::new(&contract.application, &contract.identity, BadResult, contract.operations, MAX_BOUND);
    let session = ncp::random_session();
    let open = frame::encode(&json!({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": null,
                                      "body": {"application": "echo", "contract": contract.identity, "bound": HANDSHAKE_BOUND}}), &[]).expect("encode");
    let opened = owner.handle(open).expect("open");
    let call = frame::encode(&json!({"ncp": 2, "session": session, "seq": 1, "op": "echo", "ack": frame::identity(&opened), "body": {}}), &[]).expect("encode");
    let response = frame::decode(owner.handle(call).expect("response").to_vec(), MAX_BOUND).expect("decode").message;
    assert_eq!((response["outcome"].as_str(), response["code"].as_str()), (Some("ended"), Some("owner_failure")));
    assert!(response["body"]["detail"].as_str().is_some_and(|d| d.contains("integer magnitude")));
}

#[test]
fn the_digest_check_can_be_turned_off() {
    let good = frame::encode(&json!({"a": 1}), &[]).expect("encode");
    let mut wrong = good.clone();
    let last = wrong.len() - 1;
    wrong[last] ^= 1;
    assert!(frame::decode(wrong.clone(), MAX_BOUND).is_err(), "checked: a wrong digest is a bad frame");
    let unchecked = frame::decode_with(wrong.clone(), MAX_BOUND, false).expect("unchecked");
    assert_eq!(unchecked.identity, frame::identity(&wrong), "the identity is the digest field as received");
    assert_eq!(unchecked.message, json!({"a": 1}));
    // A whole session with the check off at both ends.
    let contract = contract();
    let channel = Memory { owner: owner(Echo::default(), MAX_BOUND).without_digest_check(), inbox: VecDeque::new(),
                           drop_responses: 0, lossy: false };
    let mut client = Client::new(channel, &contract.application, &contract.identity).without_digest_check();
    client.open().expect("open");
    let arrays = all_dtypes();
    let reply = client.call("echo", json!({"v": array_body(&arrays)}), &arrays).expect("call");
    assert_eq!(reply.array_bytes(9).expect("bytes"), &arrays[9].data[..]);
    client.close().expect("close");
}

#[test]
fn a_damaged_body_is_a_bad_frame() {
    // An owner over TCP answers a request whose body was changed with the bad-frame response.
    let listener = binding::listen_tcp("127.0.0.1:0", false).expect("listen");
    let address = listener.local_addr().expect("address");
    let server = std::thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        let mut channel = binding::tcp_channel(stream).expect("channel");
        binding::serve(&mut owner(Echo::default(), MAX_BOUND), &mut channel).expect("serve");
    });
    let mut damaged = frame::encode(&json!({"a": "x".repeat(70_000)}), &[]).expect("encode");
    damaged[40_000] ^= 1;
    let mut channel = binding::connect_tcp(address, false).expect("connect");
    channel.send_frame(&damaged).expect("send");
    let response = frame::decode(channel.receive_frame(MAX_BOUND).expect("response"), MAX_BOUND).expect("decode");
    assert_eq!(response.message["code"], "bad_frame");
    server.join().expect("server");
}
