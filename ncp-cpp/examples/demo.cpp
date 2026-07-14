// Minimal C++ NCP client using the Rust core via the C ABI (ncp.h).
//
// Build (from ncp/):
//   cargo build -p ncp-cpp
//   c++ -std=c++17 -I ncp-cpp/include ncp-cpp/examples/demo.cpp \
//       -L target/debug -lncp_cpp -Wl,-rpath,target/debug -o /tmp/ncp_demo
//   /tmp/ncp_demo
//
// A C++ project would wrap these in RAII (a std::unique_ptr with ncp_string_free
// as the deleter) and a JSON library (nlohmann/json) — the point here is that the
// behavior comes from the Rust reference core. This binding is not an independent
// implementation or live interoperability/security evidence.

#include "ncp.h"
#include <iostream>
#include <memory>
#include <string>

// RAII for the heap C strings the library returns.
struct NcpFree {
  void operator()(char *p) const { ncp_string_free(p); }
};
using NcpStr = std::unique_ptr<char, NcpFree>;

static std::string take(char *p) {
  NcpStr s(p);
  return s ? std::string(s.get()) : std::string("<null>");
}

int main() {
  std::cout << "PACKAGE_VERSION = " << take(ncp_package_version()) << "\n";
  std::cout << "NCP_VERSION   = " << take(ncp_version()) << "\n";
  std::cout << "CONTRACT_SHA  = " << take(ncp_normative_contract_digest()) << "\n";
  std::cout << "BUILD_IDENTITY = " << take(ncp_build_identity()) << "\n";
  std::cout << "DEFAULT_REALM = " << take(ncp_default_realm()) << "\n";
  std::cout << "command key   = "
            << take(ncp_key_command("ncp", "uav3")) << "\n";
  std::cout << "check 1.0     = " << ncp_check_version("1.0", false) << "\n";
  std::cout << "check 1.2     = " << ncp_check_version("1.2", false) << "\n";
  std::cout << "check 0.8     = " << ncp_check_version("0.8", false) << "\n";

  const char *codec =
      "{\"encoder\":[],\"decoder\":[{\"population\":\"vel_x\",\"readout\":\"rate\","
      "\"command_channel\":\"velocity_setpoint\",\"component\":0,\"unit\":\"m/s\","
      "\"rate_range_hz\":[0,200],\"value_range\":[-1.5,1.5]}]}";
  std::cout << "decode(200hz) = "
            << take(ncp_decode_command(
                   codec, "{\"vel_x\":200.0}", 0.0,
                   /*epoch=*/"00000000-0000-4000-8000-000000000001", 7,
                   /*session_generation=*/"00000000-0000-4000-8000-0000000000a2",
                   /*session_id=*/"uav1", /*frame_id=*/nullptr, /*mode=*/nullptr,
                   /*authority_json=*/nullptr))
            << "\n";

  // Every message must carry its own kind and a compatible ncp_version.
  std::string ok = take(ncp_validate(
      "open_session",
      "{\"kind\":\"open_session\",\"ncp_version\":\"1.0\",\"session_id\":\"s1\","
      "\"network\":{\"kind\":\"builtin\",\"ref\":\"iaf_psc_alpha\"},"
      "\"identity\":{\"principal_id\":\"commander-principal-1\",\"entity_id\":\"controller-1\",\"role\":\"commander\",\"plane\":\"control\"},"
      "\"security_profile\":\"dev-loopback-insecure\","
      // Exact digest of deploy/profiles/dev-loopback-insecure.json. This admits
      // only the visibly insecure local profile; it is not a production credential.
      "\"security_state_digest\":\"1b8d5d1f0209b1c9c3131ab8787464f7d8ea17c4db7d9bc65084617fee44e21c\","
      "\"gateway_permitted\":false}"));
  bool valid = ok.find("\"kind\":\"open_session\"") != std::string::npos;
  std::cout << "validate ok   = " << (valid ? "true" : "false") << "\n";
  // ...and a version-less message is rejected (fail-closed, never coerced).
  NcpStr rejected(ncp_validate(
      "open_session",
      "{\"session_id\":\"s1\",\"network\":{\"kind\":\"builtin\",\"ref\":\"iaf_psc_alpha\"}}"));
  bool versionless_rejected = rejected.get() == nullptr;
  std::cout << "versionless   = " << (versionless_rejected ? "rejected" : "ACCEPTED?!")
            << "\n";

  // Persistent governor: the ESTOP latch must survive across calls (the
  // one-shot ncp_govern cannot latch by construction).
  NcpGovernor *gov = ncp_governor_new(
      "{\"geofence_radius_m\":5.0,\"command_timeout_ms\":500.0}");
  // Wire 1.0: every data-plane frame carries its own stream position and live
  // session; Active additionally carries a matching bounded authority lease.
  const char *active_cmd =
      "{\"kind\":\"command_frame\",\"ncp_version\":\"1.0\",\"session_id\":\"uav1\","
      "\"stream\":{\"epoch\":\"00000000-0000-4000-8000-000000000001\",\"seq\":1},"
      "\"session\":{\"generation\":\"00000000-0000-4000-8000-0000000000a2\"},"
      "\"t\":0.0,\"mode\":\"active\",\"ttl_ms\":200.0,"
      "\"channels\":{\"velocity_setpoint\":{\"data\":[1.0,0.0,0.0],\"unit\":\"m/s\"}},"
      "\"authority\":{\"session_epoch\":\"00000000-0000-4000-8000-0000000000a2\",\"term\":1,"
      "\"lease_id\":\"20000000-0000-4000-8000-000000000001\","
      "\"issuer_principal_id\":\"commander-principal-1\",\"holder_principal_id\":\"commander-principal-1\","
      "\"holder_entity_id\":\"controller-1\",\"issued_at_utc_ms\":1000,\"expires_at_utc_ms\":2000}}";
  std::string breached = take(ncp_governor_govern(
      gov, active_cmd, 1.0,
      "{\"kind\":\"sensor_frame\",\"ncp_version\":\"1.0\",\"session_id\":\"uav1\","
      "\"stream\":{\"epoch\":\"00000000-0000-4000-8000-000000000001\",\"seq\":1},"
      "\"session\":{\"generation\":\"00000000-0000-4000-8000-0000000000a2\"},\"t\":0.0,"
      "\"channels\":{\"pose_position\":{\"data\":[10.0,0.0,0.0],\"unit\":\"m\"}}}",
      1.0));
  std::string still = take(ncp_governor_govern(
      gov, active_cmd, 2.0,
      "{\"kind\":\"sensor_frame\",\"ncp_version\":\"1.0\",\"session_id\":\"uav1\","
      "\"stream\":{\"epoch\":\"00000000-0000-4000-8000-000000000001\",\"seq\":2},"
      "\"session\":{\"generation\":\"00000000-0000-4000-8000-0000000000a2\"},\"t\":0.0,"
      "\"channels\":{\"pose_position\":{\"data\":[0.0,0.0,0.0],\"unit\":\"m\"}}}",
      2.0));
  bool latched = breached.find("\"mode\":\"estop\"") != std::string::npos &&
                 still.find("\"mode\":\"estop\"") != std::string::npos &&
                 ncp_governor_is_estopped(gov) == 1;
  // Do not demonstrate a same-generation reset. Reset authorization is body-local
  // and out of scope for this binding smoke; a real reset retires the generation,
  // authority, streams, and buffers before a fresh session can actuate.
  ncp_governor_free(gov);
  std::cout << "gov latch     = " << (latched ? "latched" : "LOST?!")
            << ", reset intentionally NOT RUN\n";

  // A live actuator also needs the command-arrival buffer: it rejects replay,
  // enforces ttl_ms, and drains predictive horizons to HOLD.
  NcpActionBuffer *buffer = ncp_action_buffer_new();
  bool buffer_ingested =
      ncp_action_buffer_on_command(buffer, 4.0, active_cmd) == 0;
  std::string setpoint = take(ncp_action_buffer_active(buffer, 4.0));
  bool buffer_active = setpoint.find("velocity_setpoint") != std::string::npos;
  bool buffer_expired = ncp_action_buffer_should_hold(buffer, 4.3) == 1;
  ncp_action_buffer_free(buffer);
  std::cout << "action buffer = "
            << (buffer_ingested && buffer_active && buffer_expired ? "OK" : "FAILED")
            << "\n";

  // Exit nonzero if anything basic is wrong, so the smoke test can assert.
  bool pass = take(ncp_version()) == "1.0" && ncp_check_version("1.0", false) == 1 &&
              ncp_check_version("1.2", false) == 1 &&
              ncp_check_version("0.8", false) == 0 && valid &&
              versionless_rejected && latched && buffer_ingested && buffer_active &&
              buffer_expired;
  std::cout << (pass ? "C++ NCP demo: OK" : "C++ NCP demo: FAILED") << "\n";
  return pass ? 0 : 1;
}
