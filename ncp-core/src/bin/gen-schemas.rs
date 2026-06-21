//! Generate the JSON-Schema projection of the NCP wire **from the serde reference
//! types** — NCP owns its schemas, proto-first. The `ncp-core` serde types are the
//! conformance-locked reference implementation of `proto/ncp.proto`, and their
//! `#[serde(rename)]` carry the enum wire strings (`"V_m"`, not the proto constant
//! `V_M`), so deriving the schema from them is faithful and machine-driven (no
//! comment-parsing, no downstream-consumer dependency).
//!
//! Usage:
//!   cargo run -p ncp-core --features schema --bin gen-schemas -- [out_dir]
//! Writes `<out_dir>/<kind>.schema.json` + `index.json`. `out_dir` defaults to the
//! crate's sibling `../schemas`.

use schemars::schema_for;
use std::fs;
use std::path::PathBuf;

macro_rules! kinds {
    ($($name:literal => $ty:ty),+ $(,)?) => {
        vec![ $( ($name, serde_json::to_value(schema_for!($ty)).expect("schema serializes")) ),+ ]
    };
}

fn main() {
    let out = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../schemas"));
    fs::create_dir_all(&out).expect("create out_dir");

    // One schema per top-level wire message `kind`. Keep this list in lockstep with
    // the proto messages / the conformance corpus coverage gate.
    let schemas = kinds! {
        "capabilities"      => ncp_core::Capabilities,
        "open_session"      => ncp_core::OpenSession,
        "session_opened"    => ncp_core::SessionOpened,
        "close_session"     => ncp_core::CloseSession,
        "session_closed"    => ncp_core::SessionClosed,
        "run_request"       => ncp_core::RunRequest,
        "step_request"      => ncp_core::StepRequest,
        "sensor_frame"      => ncp_core::SensorFrame,
        "stimulus_frame"    => ncp_core::StimulusFrame,
        "observation_frame" => ncp_core::ObservationFrame,
        "command_frame"     => ncp_core::CommandFrame,
        "control_status"    => ncp_core::ControlStatus,
        "link_status"       => ncp_core::LinkStatus,
    };

    let mut names: Vec<&str> = Vec::new();
    for (name, val) in &schemas {
        let pretty = serde_json::to_string_pretty(val).expect("pretty json");
        fs::write(out.join(format!("{name}.schema.json")), pretty + "\n").expect("write schema");
        names.push(name);
    }
    names.sort_unstable();

    let index = serde_json::json!({
        "ncp_version": ncp_core::NCP_VERSION,
        "messages": names,
        "note": "Generated from the ncp-core serde reference types \
                 (cargo run --features schema --bin gen-schemas); do not edit by hand.",
    });
    fs::write(
        out.join("index.json"),
        serde_json::to_string_pretty(&index).expect("pretty index") + "\n",
    )
    .expect("write index");

    eprintln!(
        "wrote {} schemas + index.json to {}",
        schemas.len(),
        out.display()
    );
}
