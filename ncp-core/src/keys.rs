//! The NCP key scheme — the four-plane addressing the transport bindings use.
//!
//! Perception and action are **separate planes** with different QoS, rate and
//! safety requirements, so they ride separate keys. The control-plane RPC
//! (session lifecycle) is a fourth, rare, request/reply key family. Per-entity sub-keys
//! (`…/sensor/imu`, `…/command/cmd_vel`) extend each plane for the multi-sensor /
//! multi-actuator case; subscribers wildcard with `**`.
//!
//! ```text
//! {realm}/rpc/{request_kind}                   control-plane RPC   (exact query key; server declares {realm}/rpc/*)
//! {realm}/session/{id}/sensor[/{name}]         perception plane    (pub/sub, best-effort DROP)
//! {realm}/session/{id}/command[/{name}]         action plane        (pub/sub, best-effort DROP + express; ttl_ms is plant-side, safety-gated)
//! {realm}/session/{id}/observation              neural/diagnostic   (body publishes; observer subscribes read-only)
//! ```

/// Default realm (key-expression prefix) — a **neutral, project-agnostic** fallback.
/// A realm is *addressing*, not a credential: every peer that shares a deployment
/// agrees on one realm string so their keyspaces line up. NCP names no consumer here;
/// a deployment picks its own realm (via `Keys::new` / `ZenohBus::open_realm` / the
/// `NCP_REALM` env var). E.g. an Engram fleet might standardise on `"engram/ncp"`, and
/// its consumers (a prisoma observer, a crebain bridge) target that same string — that
/// choice lives in the *deployment*, not in the protocol.
pub const DEFAULT_REALM: &str = "ncp";

/// Request kinds carried by the lifecycle control plane. Wire 0.7 routes each
/// verb on a distinct key so transport ACLs can grant `open_session` without also
/// granting `step_request`, `run_request`, or cross-session `close_session`.
pub const RPC_REQUEST_KINDS: &[&str] = &[
    "open_session",
    "step_request",
    "run_request",
    "close_session",
];

/// Is `s` safe to interpolate into a single key segment? A valid segment is
/// non-empty and contains none of the Zenoh key-expression delimiters/wildcards
/// (`/` `*` `$` `#` `?`) nor any whitespace/control character or Unicode BOM
/// (`U+FEFF`, treated as whitespace by JavaScript). The transport boundary
/// (`ncp-zenoh`) rejects on this; the key builders `assert!` on it so a
/// caller passing a wildcard-bearing id (key-injection / cross-session leak) is
/// caught in both debug and release builds (fail-closed).
pub fn valid_id_segment(s: &str) -> bool {
    !s.is_empty()
        && !s.chars().any(|c| {
            matches!(c, '/' | '*' | '$' | '#' | '?' | '\u{feff}')
                || c.is_whitespace()
                || c.is_control()
        })
}

/// Is `realm` safe to use as a key-expression prefix? Multi-segment realms are
/// supported (`"engram/ncp"`), but every segment must satisfy the same injection
/// guard as a session/entity id. Leading, trailing, or repeated `/` therefore
/// fail, as do wildcards and control/whitespace characters.
pub fn valid_realm(realm: &str) -> bool {
    !realm.is_empty() && realm.split('/').all(valid_id_segment)
}

/// Error returned by [`Keys::try_new`] for an unsafe realm prefix.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InvalidRealm(pub String);

impl std::fmt::Display for InvalidRealm {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "invalid NCP realm key prefix: {:?}", self.0)
    }
}

impl std::error::Error for InvalidRealm {}

/// Error returned by fallible builders when a session/entity id is unsafe to
/// interpolate into one key-expression segment.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InvalidKeySegment {
    pub label: &'static str,
    pub value: String,
}

impl std::fmt::Display for InvalidKeySegment {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "invalid NCP {} key segment: {:?}",
            self.label, self.value
        )
    }
}

impl std::error::Error for InvalidKeySegment {}

/// Key-expression builders for a given realm.
#[derive(Clone, Debug)]
pub struct Keys {
    realm: String,
}

impl Default for Keys {
    fn default() -> Self {
        Self {
            realm: DEFAULT_REALM.to_string(),
        }
    }
}

impl Keys {
    /// Construct keys for a validated realm, panicking on programmer error.
    /// User/config input should use [`Self::try_new`] so invalid input becomes a
    /// normal startup error instead of a panic.
    pub fn new(realm: impl Into<String>) -> Self {
        let realm = realm.into();
        assert!(valid_realm(&realm), "invalid NCP realm: {realm:?}");
        Self { realm }
    }

    /// Fallible constructor for environment/config supplied realms.
    pub fn try_new(realm: impl Into<String>) -> Result<Self, InvalidRealm> {
        let realm = realm.into();
        if valid_realm(&realm) {
            Ok(Self { realm })
        } else {
            Err(InvalidRealm(realm))
        }
    }

    /// Revalidate this instance defensively at a transport boundary.
    pub fn validate(&self) -> Result<(), InvalidRealm> {
        if valid_realm(&self.realm) {
            Ok(())
        } else {
            Err(InvalidRealm(self.realm.clone()))
        }
    }

    /// Validated realm prefix chosen at construction.
    pub fn realm(&self) -> &str {
        self.validate()
            .expect("Keys invariants guarantee a valid NCP realm");
        &self.realm
    }

    /// Control-plane RPC prefix. It is not itself queried in wire 0.7; use
    /// [`Self::rpc_for_kind`] for a request or [`Self::rpc_glob`] for a server.
    pub fn rpc(&self) -> String {
        format!("{}/rpc", self.realm())
    }

    /// Exact query key for one lifecycle request kind.
    pub fn rpc_for_kind(&self, kind: &str) -> Result<String, &'static str> {
        if RPC_REQUEST_KINDS.contains(&kind) {
            Ok(format!("{}/{}", self.rpc(), kind))
        } else {
            Err("not an NCP lifecycle RPC request kind")
        }
    }

    /// Queryable expression covering all lifecycle request keys.
    pub fn rpc_glob(&self) -> String {
        format!("{}/*", self.rpc())
    }

    fn try_session(&self, id: &str) -> Result<String, InvalidKeySegment> {
        if !valid_id_segment(id) {
            return Err(InvalidKeySegment {
                label: "session id",
                value: id.to_owned(),
            });
        }
        Ok(format!("{}/session/{}", self.realm(), id))
    }

    fn session(&self, id: &str) -> String {
        self.try_session(id)
            .unwrap_or_else(|error| panic!("{error}"))
    }

    /// Perception plane for a session (all sensors): `…/session/{id}/sensor`.
    pub fn sensor(&self, id: &str) -> String {
        format!("{}/sensor", self.session(id))
    }

    /// Fallible perception-plane builder for untrusted/configured ids.
    pub fn try_sensor(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/sensor", self.try_session(id)?))
    }

    /// One named sensor on the perception plane: `…/session/{id}/sensor/{name}`.
    pub fn sensor_named(&self, id: &str, name: &str) -> String {
        self.try_sensor_named(id, name)
            .unwrap_or_else(|error| panic!("{error}"))
    }

    /// Fallible named-sensor builder for untrusted/configured ids.
    pub fn try_sensor_named(&self, id: &str, name: &str) -> Result<String, InvalidKeySegment> {
        if !valid_id_segment(name) {
            return Err(InvalidKeySegment {
                label: "sensor name",
                value: name.to_owned(),
            });
        }
        Ok(format!("{}/sensor/{name}", self.try_session(id)?))
    }

    /// Action plane for a session (all actuators): `…/session/{id}/command`.
    pub fn command(&self, id: &str) -> String {
        format!("{}/command", self.session(id))
    }

    /// Fallible action-plane builder for untrusted/configured ids.
    pub fn try_command(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/command", self.try_session(id)?))
    }

    /// One named actuator on the action plane: `…/session/{id}/command/{name}`.
    pub fn command_named(&self, id: &str, name: &str) -> String {
        self.try_command_named(id, name)
            .unwrap_or_else(|error| panic!("{error}"))
    }

    /// Fallible named-actuator builder for untrusted/configured ids.
    pub fn try_command_named(&self, id: &str, name: &str) -> Result<String, InvalidKeySegment> {
        if !valid_id_segment(name) {
            return Err(InvalidKeySegment {
                label: "command name",
                value: name.to_owned(),
            });
        }
        Ok(format!("{}/command/{name}", self.try_session(id)?))
    }

    /// Observation/diagnostic plane (the free read-only observer tap).
    pub fn observation(&self, id: &str) -> String {
        format!("{}/observation", self.session(id))
    }

    /// Fallible observation-plane builder for untrusted/configured ids.
    pub fn try_observation(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/observation", self.try_session(id)?))
    }

    /// All of a session's sensors (wildcard) — e.g. a controller subscribing to
    /// every sensor of one UAV, whatever the count: `…/session/{id}/sensor/**`.
    pub fn sensor_glob(&self, id: &str) -> String {
        format!("{}/sensor/**", self.session(id))
    }

    pub fn try_sensor_glob(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/sensor/**", self.try_session(id)?))
    }

    /// All of a session's actuators: `…/session/{id}/command/**`.
    pub fn command_glob(&self, id: &str) -> String {
        format!("{}/command/**", self.session(id))
    }

    pub fn try_command_glob(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/command/**", self.try_session(id)?))
    }

    /// A wildcard over every plane of a session, e.g. for an observer tap.
    pub fn session_glob(&self, id: &str) -> String {
        format!("{}/**", self.session(id))
    }

    pub fn try_session_glob(&self, id: &str) -> Result<String, InvalidKeySegment> {
        Ok(format!("{}/**", self.try_session(id)?))
    }

    /// Every session in the realm — the fleet wildcard (all UAVs):
    /// `{realm}/session/**`. Per-entity `seq` is scoped to each named
    /// sensor/actuator stream, so a `LinkMonitor`/`ActionBuffer` is instantiated
    /// per `(session, entity)`.
    pub fn fleet_glob(&self) -> String {
        format!("{}/session/**", self.realm())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn key_scheme() {
        // The default realm is the neutral "ncp"; a deployment overrides it.
        let k = Keys::default();
        assert_eq!(k.rpc(), "ncp/rpc");
        assert_eq!(k.rpc_glob(), "ncp/rpc/*");
        assert_eq!(
            k.rpc_for_kind("open_session").unwrap(),
            "ncp/rpc/open_session"
        );
        assert!(k.rpc_for_kind("session_opened").is_err());
        assert_eq!(k.sensor("s1"), "ncp/session/s1/sensor");
        assert_eq!(k.sensor_named("s1", "imu"), "ncp/session/s1/sensor/imu");
        assert_eq!(
            k.command_named("s1", "cmd_vel"),
            "ncp/session/s1/command/cmd_vel"
        );
        assert_eq!(k.observation("s1"), "ncp/session/s1/observation");
        assert_eq!(k.session_glob("s1"), "ncp/session/s1/**");
    }

    #[test]
    fn realm_is_an_explicit_deployment_choice() {
        // A deployment (e.g. an Engram fleet) picks its own realm; NCP names no
        // consumer in its default. The key builders interpolate whatever is given.
        let k = Keys::new("engram/ncp");
        assert_eq!(k.rpc(), "engram/ncp/rpc");
        assert_eq!(
            k.rpc_for_kind("step_request").unwrap(),
            "engram/ncp/rpc/step_request"
        );
        assert_eq!(k.observation("uav3"), "engram/ncp/session/uav3/observation");
    }

    #[test]
    fn valid_id_segment_accepts_normal_ids() {
        assert!(valid_id_segment("s1"));
        assert!(valid_id_segment("uav3"));
        assert!(valid_id_segment("cmd_vel"));
        assert!(valid_id_segment("imu-0.cam"));
    }

    #[test]
    fn valid_id_segment_rejects_empty() {
        assert!(!valid_id_segment(""));
    }

    #[test]
    fn valid_id_segment_rejects_slash() {
        // A slash would smuggle the id into adjacent key segments
        // (cross-session/cross-plane leak).
        assert!(!valid_id_segment("s1/command"));
        assert!(!valid_id_segment("a/b"));
    }

    #[test]
    fn valid_id_segment_rejects_wildcards_and_whitespace() {
        for bad in [
            "*",
            "**",
            "s*",
            "a$b",
            "a#b",
            "a?b",
            "s 1",
            "s\t1",
            "s\n1",
            "s\u{00a0}1",
            "s\u{feff}1",
            "s\0x",
        ] {
            assert!(!valid_id_segment(bad), "{bad:?} should be rejected");
        }
    }

    #[test]
    fn realm_validation_allows_segments_but_rejects_key_injection() {
        for good in ["ncp", "engram/ncp", "lab-1/robotics.ncp"] {
            assert!(valid_realm(good), "{good:?} should be a valid realm");
            assert!(Keys::try_new(good).is_ok());
        }
        for bad in [
            "",
            "/ncp",
            "ncp/",
            "ncp//fleet",
            "ncp/**",
            "ncp/$*",
            "ncp/robot\ncommand",
        ] {
            assert!(!valid_realm(bad), "{bad:?} should be rejected");
            assert!(Keys::try_new(bad).is_err());
        }
    }

    #[test]
    fn fallible_builders_reject_session_and_entity_injection() {
        let keys = Keys::default();
        assert!(keys.try_sensor("bad/*").is_err());
        assert!(keys.try_command("bad/id").is_err());
        assert!(keys.try_observation("").is_err());
        assert!(keys.try_sensor_named("s1", "imu*").is_err());
        assert!(keys.try_command_named("s1", "motor/0").is_err());
        assert!(keys.try_session_glob("s1/**").is_err());
        assert_eq!(keys.try_sensor("s1").unwrap(), keys.sensor("s1"));
        assert_eq!(
            keys.try_command_named("s1", "motor0").unwrap(),
            keys.command_named("s1", "motor0")
        );
    }

    #[test]
    #[should_panic]
    fn session_key_builder_rejects_wildcard_id() {
        // The builder `assert!`s the id; a wildcard id must trip it in both
        // debug and release builds (fail-closed key-injection guard).
        let _ = Keys::default().sensor("../*");
    }
}
