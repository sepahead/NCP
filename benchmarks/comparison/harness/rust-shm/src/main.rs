//! The shared-memory arm of the comparison benchmark (see ../../PROTOCOL-4.md): iceoryx2 0.10.0,
//! request-response between two processes over zero-copy shared memory.
//!
//! bench-shm iox2-server NAME                      creates the service NAME, prints "ready NAME",
//!                                                 and serves until it is stopped
//! bench-shm iox2-client CALLS WARMUP SPIKES NAME  times CALLS calls after WARMUP calls
//!
//! The messages are those of harness/rust: a 16-byte request (call index, spike count) and the
//! request header with N spikes back, senders as little-endian u32, then times as little-endian
//! f64. With BENCH_SHA256=1 in the environment of both ends, each sender appends the SHA-256 digest
//! of its message, and each receiver computes it again and compares: the integrity check of NCP 2.
//! Both ends poll without sleeping, as iceoryx2's own benchmarks do: each keeps one core busy.
use iceoryx2::prelude::*;
use serde_json::json;
use std::collections::HashMap;
use std::time::Instant;

/// The largest response: the header, 87381 spikes, and a digest.
const MAX_RESPONSE: usize = 16 + 12 * 87381 + 32;
/// The largest request: the header and a digest.
const MAX_REQUEST: usize = 16 + 32;

mod integrity {
    use sha2::{Digest, Sha256};

    /// Whether this process appends and checks digests (BENCH_SHA256=1).
    pub fn on() -> bool {
        std::env::var("BENCH_SHA256").as_deref() == Ok("1")
    }

    /// Append the SHA-256 digest of the message.
    pub fn seal(mut data: Vec<u8>) -> Vec<u8> {
        let digest = Sha256::digest(&data);
        data.extend_from_slice(&digest);
        data
    }

    /// Compute the digest of the message again, compare it, and return the message without it.
    pub fn open(data: &[u8]) -> &[u8] {
        let (body, digest) = data.split_at(data.len().checked_sub(32).expect("sealed message"));
        assert!(Sha256::digest(body).as_slice() == digest, "digest mismatch");
        body
    }
}

/// N spikes from the benchmark generator, as in harness/rust.
fn spikes_bytes(n: usize) -> Vec<u8> {
    let mut state = 0x2545_f491_4f6c_dd1d_u64;
    let (mut senders, mut times) = (Vec::with_capacity(n * 4), Vec::with_capacity(n * 8));
    for _ in 0..n {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        senders.extend_from_slice(&(((state >> 33) % 1000 + 1) as u32).to_le_bytes());
        times.extend_from_slice(&(((state >> 20) % 100) as f64 / 10.0 + 0.1).to_le_bytes());
    }
    senders.extend_from_slice(&times);
    senders
}

/// The server side, as in harness/rust: the request header, then N cached spikes.
fn respond(cache: &mut HashMap<usize, Vec<u8>>, received: &[u8]) -> Vec<u8> {
    let sealed = integrity::on();
    let request = if sealed { integrity::open(received) } else { received };
    let n = u64::from_le_bytes(request[8..16].try_into().expect("request")) as usize;
    let body = cache.entry(n).or_insert_with(|| spikes_bytes(n));
    let mut response = Vec::with_capacity(16 + body.len() + 32);
    response.extend_from_slice(&request[..16]);
    response.extend_from_slice(body);
    if sealed {
        integrity::seal(response)
    } else {
        response
    }
}

type Service = iceoryx2::service::port_factory::request_response::PortFactory<ipc::Service, [u8], (), [u8], ()>;

fn service(node: &Node<ipc::Service>, name: &str) -> Service {
    let name: ServiceName = name.try_into().expect("service name");
    node.service_builder(&name)
        .request_response::<[u8], [u8]>()
        .open_or_create()
        .expect("service")
}

fn server(name: &str) {
    let node = NodeBuilder::new().create::<ipc::Service>().expect("node");
    let service = service(&node, name);
    let server = service
        .server_builder()
        .initial_max_slice_len(MAX_RESPONSE)
        .create()
        .expect("server");
    println!("ready {name}");
    let mut cache = HashMap::new();
    loop {
        while let Some(request) = server.receive().expect("receive") {
            let response = respond(&mut cache, request.payload());
            request
                .loan_slice_uninit(response.len())
                .expect("loan")
                .write_from_slice(&response)
                .send()
                .expect("send");
        }
        std::hint::spin_loop();
    }
}

fn client(args: &[String]) {
    let calls: usize = args[2].parse().expect("calls");
    let warmup: usize = args[3].parse().expect("warmup");
    let spikes: usize = args[4].parse().expect("spikes");
    let node = NodeBuilder::new().create::<ipc::Service>().expect("node");
    let service = service(&node, &args[5]);
    let client = service
        .client_builder()
        .initial_max_slice_len(MAX_REQUEST)
        .create()
        .expect("client");
    let sealed = integrity::on();
    let mut times = Vec::with_capacity(calls);
    for index in 0..warmup + calls {
        let started = Instant::now();
        let mut data = (index as u64).to_le_bytes().to_vec();
        data.extend_from_slice(&(spikes as u64).to_le_bytes());
        let sent = if sealed { integrity::seal(data.clone()) } else { data.clone() };
        let pending = client
            .loan_slice_uninit(sent.len())
            .expect("loan")
            .write_from_slice(&sent)
            .send()
            .expect("send");
        let response = loop {
            if let Some(response) = pending.receive().expect("receive") {
                break response;
            }
            std::hint::spin_loop();
        };
        let received = response.payload();
        let body = if sealed { integrity::open(received) } else { received };
        assert!(body.len() == 16 + 12 * spikes && body[..16] == data[..], "wrong response");
        if index >= warmup {
            times.push(started.elapsed().as_secs_f64() * 1e6);
        }
    }
    times.sort_by(|a, b| a.total_cmp(b));
    let pick = |q: f64| times[((times.len() - 1) as f64 * q).round() as usize];
    let quantiles: Vec<f64> = (0..=100).map(|i| pick(f64::from(i) / 100.0)).collect();
    let mean = times.iter().sum::<f64>() / times.len() as f64;
    let stack = if sealed {
        "iceoryx2 0.10.0, shared memory, busy polling, SHA-256 at both ends"
    } else {
        "iceoryx2 0.10.0, shared memory, busy polling"
    };
    println!(
        "{}",
        json!({"calls": times.len(), "warmup": warmup, "spikes": spikes, "median_us": pick(0.5),
               "p05_us": pick(0.05), "p95_us": pick(0.95), "p99_us": pick(0.99), "mean_us": mean,
               "min_us": times[0], "max_us": times[times.len() - 1], "quantiles_us": quantiles,
               "stack": stack})
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("iox2-server") => server(&args[2]),
        Some("iox2-client") => client(&args),
        _ => panic!("usage: bench-shm iox2-server NAME | iox2-client CALLS WARMUP SPIKES NAME"),
    }
}
