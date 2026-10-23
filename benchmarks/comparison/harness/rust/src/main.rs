//! Rust comparison arms (see ../../PROTOCOL.md). One binary, one arm per subcommand:
//!
//! bench raw-server                          answers on stdin and stdout
//! bench raw-client CALLS WARMUP SPIKES -- SERVER...
//! bench grpc-server                         prints "ready 127.0.0.1:PORT"
//! bench grpc-client CALLS WARMUP SPIKES ADDRESS
//! bench zenoh-server                        prints "ready tcp/127.0.0.1:PORT"
//! bench zenoh-client CALLS WARMUP SPIKES ENDPOINT
//!
//! Every arm sends a 16-byte request (call index, spike count) and gets the request header and
//! N spikes back: senders as little-endian u32, then times as little-endian f64.
use serde_json::json;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::time::Instant;

fn spikes_bytes(n: usize) -> Vec<u8> {
    let mut state = 0x2545_f491_4f6c_dd1d_u64;
    let (mut senders, mut times) = (Vec::with_capacity(n * 4), Vec::with_capacity(n * 8));
    for _ in 0..n {
        state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
        senders.extend_from_slice(&(((state >> 33) % 1000 + 1) as u32).to_le_bytes());
        times.extend_from_slice(&(((state >> 20) % 100) as f64 / 10.0 + 0.1).to_le_bytes());
    }
    senders.extend_from_slice(&times);
    senders
}

/// The server side of every arm: the request header, then N cached spikes.
#[derive(Default)]
struct Responder {
    cache: HashMap<usize, Vec<u8>>,
}

impl Responder {
    fn respond(&mut self, request: &[u8]) -> Vec<u8> {
        let n = u64::from_le_bytes(request[8..16].try_into().expect("request")) as usize;
        let body = self.cache.entry(n).or_insert_with(|| spikes_bytes(n));
        let mut response = Vec::with_capacity(16 + body.len());
        response.extend_from_slice(&request[..16]);
        response.extend_from_slice(body);
        response
    }
}

fn request(index: usize, spikes: usize) -> Vec<u8> {
    let mut data = (index as u64).to_le_bytes().to_vec();
    data.extend_from_slice(&(spikes as u64).to_le_bytes());
    data
}

fn check(sent: &[u8], received: &[u8], spikes: usize) {
    assert!(received.len() == 16 + 12 * spikes && &received[..16] == sent, "wrong response");
}

fn report(mut times: Vec<f64>, warmup: usize, spikes: usize, extra: serde_json::Value) {
    times.sort_by(|a, b| a.total_cmp(b));
    let pick = |q: f64| times[((times.len() - 1) as f64 * q).round() as usize];
    let quantiles: Vec<f64> = (0..=100).map(|i| pick(f64::from(i) / 100.0)).collect();
    let mean = times.iter().sum::<f64>() / times.len() as f64;
    println!("{}", json!({"calls": times.len(), "warmup": warmup, "spikes": spikes, "median_us": pick(0.5),
                           "p05_us": pick(0.05), "p95_us": pick(0.95), "p99_us": pick(0.99), "mean_us": mean,
                           "min_us": times[0], "max_us": times[times.len() - 1], "quantiles_us": quantiles,
                           "stack": extra}));
}

fn numbers(args: &[String]) -> (usize, usize, usize) {
    (args[2].parse().expect("calls"), args[3].parse().expect("warmup"), args[4].parse().expect("spikes"))
}

// The raw pipe floor.

fn raw_server() {
    let (mut input, mut output) = (std::io::stdin().lock(), std::io::stdout().lock());
    let mut responder = Responder::default();
    let mut header = [0u8; 4];
    while input.read_exact(&mut header).is_ok() {
        let mut data = vec![0u8; u32::from_be_bytes(header) as usize];
        input.read_exact(&mut data).expect("request");
        let response = responder.respond(&data);
        output.write_all(&(response.len() as u32).to_be_bytes()).expect("write");
        output.write_all(&response).expect("write");
        output.flush().expect("flush");
    }
}

fn raw_client(args: &[String]) {
    let (calls, warmup, spikes) = numbers(args);
    let mut child = std::process::Command::new(&args[6]).args(&args[7..]).stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped()).spawn().expect("spawn");
    let (mut writer, mut reader) = (child.stdin.take().expect("stdin"), child.stdout.take().expect("stdout"));
    let mut times = Vec::with_capacity(calls);
    let mut buffer = Vec::new();
    for index in 0..warmup + calls {
        let started = Instant::now();
        let data = request(index, spikes);
        let mut frame = (data.len() as u32).to_be_bytes().to_vec();
        frame.extend_from_slice(&data);
        writer.write_all(&frame).expect("write");
        let mut header = [0u8; 4];
        reader.read_exact(&mut header).expect("read");
        buffer.resize(u32::from_be_bytes(header) as usize, 0);
        reader.read_exact(&mut buffer).expect("read");
        check(&data, &buffer, spikes);
        if index >= warmup {
            times.push(started.elapsed().as_secs_f64() * 1e6);
        }
    }
    drop(writer);
    child.wait().expect("wait");
    report(times, warmup, spikes, json!("raw pipe"));
}

// gRPC with tonic: one unary method whose request and response hold one bytes field.

#[derive(Clone, PartialEq, prost::Message)]
struct Message {
    #[prost(bytes = "bytes", tag = "1")]
    data: bytes::Bytes,
}

mod grpc {
    use super::{Message, Responder};
    use std::sync::{Arc, Mutex};
    use std::task::{Context, Poll};
    use tonic::codegen::{http, Body, BoxFuture, Service, StdError};

    pub const PATH: &str = "/bench.Echo/Call";

    #[derive(Clone, Default)]
    pub struct EchoService {
        responder: Arc<Mutex<Responder>>,
    }

    struct Call(Arc<Mutex<Responder>>);

    impl tonic::server::UnaryService<Message> for Call {
        type Response = Message;
        type Future = BoxFuture<tonic::Response<Message>, tonic::Status>;
        fn call(&mut self, request: tonic::Request<Message>) -> Self::Future {
            let response = self.0.lock().expect("responder").respond(&request.into_inner().data);
            Box::pin(async move { Ok(tonic::Response::new(Message { data: response.into() })) })
        }
    }

    impl<B> Service<http::Request<B>> for EchoService
    where
        B: Body + Send + 'static,
        B::Error: Into<StdError> + Send + 'static,
    {
        type Response = http::Response<tonic::body::Body>;
        type Error = std::convert::Infallible;
        type Future = BoxFuture<Self::Response, Self::Error>;
        fn poll_ready(&mut self, _: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
            Poll::Ready(Ok(()))
        }
        fn call(&mut self, request: http::Request<B>) -> Self::Future {
            let responder = self.responder.clone();
            Box::pin(async move {
                if request.uri().path() != PATH {
                    return Ok(tonic::Status::unimplemented("unknown method").into_http());
                }
                let mut grpc = tonic::server::Grpc::new(tonic_prost::ProstCodec::default());
                Ok(grpc.unary(Call(responder), request).await)
            })
        }
    }

    impl tonic::server::NamedService for EchoService {
        const NAME: &'static str = "bench.Echo";
    }
}

fn runtime() -> tokio::runtime::Runtime {
    tokio::runtime::Builder::new_current_thread().enable_all().build().expect("runtime")
}

fn grpc_server() {
    runtime().block_on(async {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.expect("bind");
        println!("ready {}", listener.local_addr().expect("address"));
        std::io::stdout().flush().expect("flush");
        let incoming = futures_incoming(listener);
        tonic::transport::Server::builder()
            .tcp_nodelay(true)
            .add_service(grpc::EchoService::default())
            .serve_with_incoming(incoming)
            .await
            .expect("serve");
    });
}

fn futures_incoming(listener: tokio::net::TcpListener) -> impl tokio_stream_like::Stream {
    tokio_stream_like::Incoming(listener)
}

mod tokio_stream_like {
    //! A minimal stream of accepted TCP connections with TCP_NODELAY, for serve_with_incoming.
    use std::pin::Pin;
    use std::task::{Context, Poll};
    pub trait Stream: tonic::codegen::tokio_stream::Stream<Item = std::io::Result<tokio::net::TcpStream>> + Send + 'static {}
    impl<T: tonic::codegen::tokio_stream::Stream<Item = std::io::Result<tokio::net::TcpStream>> + Send + 'static> Stream for T {}
    pub struct Incoming(pub tokio::net::TcpListener);
    impl tonic::codegen::tokio_stream::Stream for Incoming {
        type Item = std::io::Result<tokio::net::TcpStream>;
        fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
            match self.0.poll_accept(cx) {
                Poll::Ready(Ok((stream, _))) => Poll::Ready(Some(stream.set_nodelay(true).map(|()| stream))),
                Poll::Ready(Err(error)) => Poll::Ready(Some(Err(error))),
                Poll::Pending => Poll::Pending,
            }
        }
    }
}

fn grpc_client(args: &[String]) {
    let (calls, warmup, spikes) = numbers(args);
    let address = format!("http://{}", args[5]);
    runtime().block_on(async {
        let channel = tonic::transport::Endpoint::from_shared(address).expect("endpoint").tcp_nodelay(true)
            .connect().await.expect("connect");
        let mut client = tonic::client::Grpc::new(channel)
            .max_decoding_message_size(64 << 20)
            .max_encoding_message_size(64 << 20);
        let mut times = Vec::with_capacity(calls);
        for index in 0..warmup + calls {
            let started = Instant::now();
            let data = request(index, spikes);
            client.ready().await.expect("ready");
            let response = client
                .unary(tonic::Request::new(Message { data: data.clone().into() }),
                       tonic::codegen::http::uri::PathAndQuery::from_static(grpc::PATH),
                       tonic_prost::ProstCodec::<Message, Message>::default())
                .await
                .expect("call");
            check(&data, &response.into_inner().data, spikes);
            if index >= warmup {
                times.push(started.elapsed().as_secs_f64() * 1e6);
            }
        }
        report(times, warmup, spikes, json!("tonic 0.14, TCP loopback"));
    });
}

// Zenoh query/reply, peer mode, TCP loopback, no multicast scouting.

fn zenoh_config(name: &str, endpoint: &str) -> zenoh::Config {
    let mut config = zenoh::Config::default();
    config.insert_json5("mode", r#""peer""#).expect("mode");
    config.insert_json5("scouting/multicast/enabled", "false").expect("scouting");
    config.insert_json5(&format!("{name}/endpoints"), &format!(r#"["{endpoint}"]"#)).expect("endpoints");
    config
}

fn zenoh_server() {
    let port = std::net::TcpListener::bind("127.0.0.1:0").expect("probe").local_addr().expect("address").port();
    let endpoint = format!("tcp/127.0.0.1:{port}");
    tokio::runtime::Builder::new_multi_thread().enable_all().build().expect("runtime").block_on(async {
        let session = zenoh::open(zenoh_config("listen", &endpoint)).await.expect("open");
        let queryable = session.declare_queryable("bench/echo").await.expect("queryable");
        println!("ready {endpoint}");
        std::io::stdout().flush().expect("flush");
        let mut responder = Responder::default();
        while let Ok(query) = queryable.recv_async().await {
            let data = query.payload().map(|payload| payload.to_bytes().into_owned()).unwrap_or_default();
            query.reply("bench/echo", responder.respond(&data)).await.expect("reply");
        }
    });
}

fn zenoh_client(args: &[String]) {
    let (calls, warmup, spikes) = numbers(args);
    let endpoint = args[5].clone();
    tokio::runtime::Builder::new_multi_thread().enable_all().build().expect("runtime").block_on(async {
        let session = zenoh::open(zenoh_config("connect", &endpoint)).await.expect("open");
        let querier = session.declare_querier("bench/echo").timeout(std::time::Duration::from_secs(10)).await.expect("querier");
        let deadline = Instant::now() + std::time::Duration::from_secs(10);
        while session.info().peers_zid().await.next().is_none() {
            assert!(Instant::now() < deadline, "no Zenoh peer");
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        let mut times = Vec::with_capacity(calls);
        for index in 0..warmup + calls {
            let started = Instant::now();
            let data = request(index, spikes);
            let replies = querier.get().payload(data.clone()).await.expect("get");
            let reply = replies.recv_async().await.expect("reply");
            let received = reply.result().expect("reply ok").payload().to_bytes().into_owned();
            check(&data, &received, spikes);
            if index >= warmup {
                times.push(started.elapsed().as_secs_f64() * 1e6);
            }
        }
        report(times, warmup, spikes, json!("zenoh 1.9.0, TCP loopback"));
        drop(session);
    });
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args[1].as_str() {
        "raw-server" => raw_server(),
        "raw-client" => raw_client(&args),
        "grpc-server" => grpc_server(),
        "grpc-client" => grpc_client(&args),
        "zenoh-server" => zenoh_server(),
        "zenoh-client" => zenoh_client(&args),
        other => panic!("unknown arm {other}"),
    }
}
