//! Quarantined loopback-only TLS 1.3 authenticated-ingress prototype.
//!
//! This crate is deliberately outside the NCP workspace and packages. It proves
//! only that one process can bind a verified client leaf certificate to an
//! immutable, bounded NCP payload. The resulting context is diagnostic input to
//! a disposable mock: it is not an authority lease, session, receipt, capability,
//! plant admission, or production-security result.
#![deny(missing_docs)]

use std::{
    collections::HashSet,
    error::Error,
    fmt::{self, Debug, Display, Formatter},
    net::IpAddr,
    sync::{Arc, RwLock},
    time::Duration,
};

use ncp_core::{IdentityClaim, Plane, PrincipalRole};
use rustls::{
    pki_types::{CertificateDer, PrivateKeyDer},
    server::{NoServerSessionStorage, WebPkiClientVerifier},
    version, RootCertStore, ServerConfig,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::{
    io::AsyncReadExt,
    net::{TcpListener, TcpStream},
    time::timeout,
};
use tokio_rustls::TlsAcceptor;

/// Exact schema literal accepted for prototype manifest documents.
pub const MANIFEST_SCHEMA: &str = "ncp.prototype.tls-ingress-manifest.v1";
/// Sole ALPN protocol offered by the quarantined endpoint.
pub const ALPN_PROTOCOL: &[u8] = b"ncp-prototype-a/1";
/// Maximum manifest bytes checked before parsing or semantic allocation.
pub const MAX_MANIFEST_BYTES: usize = 65_536;
/// Maximum principals accepted in one prototype manifest.
pub const MAX_PRINCIPALS: usize = 64;
/// Maximum grants accepted for one principal.
pub const MAX_GRANTS_PER_PRINCIPAL: usize = 32;
/// Maximum grants accepted across one manifest.
pub const MAX_TOTAL_GRANTS: usize = 256;

/// Stable categories for fail-closed prototype errors.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[non_exhaustive]
pub enum ErrorCode {
    /// The local endpoint or cryptographic configuration is invalid.
    Configuration,
    /// The manifest exceeded its byte or collection bounds.
    ManifestBounds,
    /// Exact manifest bytes did not match the supplied SHA-256.
    ManifestDigest,
    /// The manifest shape or closed values are invalid.
    ManifestInvalid,
    /// A lower manifest generation attempted to replace the current one.
    ManifestRollback,
    /// Different bytes claimed the already-current generation.
    ManifestEquivocation,
    /// No exact certificate and endpoint grant exists.
    ManifestDenied,
    /// TCP address or connection ownership checks failed.
    Transport,
    /// A bounded accept, handshake, or frame read expired.
    Timeout,
    /// TLS authentication or handshake processing failed.
    Tls,
    /// TLS version, handshake kind, or ALPN did not match the profile.
    Protocol,
    /// The declared frame length was zero or too large.
    FrameBounds,
    /// The frame, TLS closure, or close-notify boundary was incomplete.
    FrameIncomplete,
    /// Trailing application bytes or a second frame were present.
    FrameTrailing,
    /// The exact payload failed bounded NCP parsing or validation.
    PayloadInvalid,
    /// Payload identity or message class did not match the transport binding.
    IdentityMismatch,
}

/// One categorized, bounded-detail prototype failure.
#[derive(Debug, PartialEq, Eq)]
pub struct IngressError {
    code: ErrorCode,
    detail: String,
}

impl IngressError {
    fn new(code: ErrorCode, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }

    /// Returns the stable failure category.
    pub const fn code(&self) -> ErrorCode {
        self.code
    }

    /// Returns diagnostic detail that must not be parsed as policy.
    pub fn detail(&self) -> &str {
        &self.detail
    }
}

impl Display for IngressError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        write!(formatter, "{:?}: {}", self.code, self.detail)
    }
}

impl Error for IngressError {}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(64);
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn valid_literal(value: &str, max_bytes: usize) -> bool {
    !value.is_empty()
        && value.len() <= max_bytes
        && value.is_ascii()
        && !value.bytes().any(|byte| {
            byte.is_ascii_control()
                || byte.is_ascii_whitespace()
                || matches!(byte, b'*' | b'?' | b'[' | b']' | b'{' | b'}' | b'#')
        })
}

fn closed_role(role: PrincipalRole) -> bool {
    !matches!(role, PrincipalRole::Unknown)
}

fn closed_plane(plane: Plane) -> bool {
    !matches!(plane, Plane::Unknown)
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Grant {
    route: String,
    plane: Plane,
    message_class: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PrincipalEntry {
    principal_id: String,
    entity_id: String,
    role: PrincipalRole,
    certificate_sha256: String,
    grants: Vec<Grant>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestDocument {
    schema: String,
    generation: u64,
    default_deny: bool,
    principals: Vec<PrincipalEntry>,
}

#[derive(Debug)]
struct ManifestSnapshot {
    generation: u64,
    digest: String,
    _exact_bytes: Box<[u8]>,
    principals: Box<[PrincipalEntry]>,
}

impl ManifestSnapshot {
    fn parse(bytes: &[u8], expected_sha256: &str) -> Result<Self, IngressError> {
        if bytes.is_empty() || bytes.len() > MAX_MANIFEST_BYTES {
            return Err(IngressError::new(
                ErrorCode::ManifestBounds,
                format!(
                    "manifest length {} is outside 1..={MAX_MANIFEST_BYTES}",
                    bytes.len()
                ),
            ));
        }
        if !is_sha256_hex(expected_sha256) {
            return Err(IngressError::new(
                ErrorCode::ManifestDigest,
                "expected manifest digest is not lowercase SHA-256 hex",
            ));
        }
        let actual_sha256 = sha256_hex(bytes);
        if actual_sha256 != expected_sha256 {
            return Err(IngressError::new(
                ErrorCode::ManifestDigest,
                "manifest exact-byte SHA-256 does not match the supplied content address",
            ));
        }
        ncp_core::bounded_json::preflight(bytes).map_err(|error| {
            IngressError::new(
                ErrorCode::ManifestInvalid,
                format!("manifest bounded-JSON preflight failed: {error}"),
            )
        })?;
        let document: ManifestDocument = serde_json::from_slice(bytes).map_err(|error| {
            IngressError::new(
                ErrorCode::ManifestInvalid,
                format!("manifest shape is invalid: {error}"),
            )
        })?;
        document.validate()?;
        Ok(Self {
            generation: document.generation,
            digest: actual_sha256,
            _exact_bytes: bytes.to_vec().into_boxed_slice(),
            principals: document.principals.into_boxed_slice(),
        })
    }

    fn entry_for_leaf(&self, leaf_sha256: &str) -> Option<&PrincipalEntry> {
        self.principals
            .iter()
            .find(|entry| entry.certificate_sha256 == leaf_sha256)
    }

    fn permits(&self, leaf_sha256: &str, profile: &EndpointProfile) -> bool {
        self.entry_for_leaf(leaf_sha256).is_some_and(|entry| {
            entry.grants.iter().any(|grant| {
                grant.route == profile.route
                    && grant.plane == profile.plane
                    && grant.message_class == profile.message_class
            })
        })
    }
}

impl ManifestDocument {
    fn validate(&self) -> Result<(), IngressError> {
        if self.schema != MANIFEST_SCHEMA {
            return Err(IngressError::new(
                ErrorCode::ManifestInvalid,
                "manifest schema literal is unknown",
            ));
        }
        if self.generation == 0 {
            return Err(IngressError::new(
                ErrorCode::ManifestInvalid,
                "manifest generation must be positive",
            ));
        }
        if !self.default_deny {
            return Err(IngressError::new(
                ErrorCode::ManifestInvalid,
                "manifest must explicitly set default_deny=true",
            ));
        }
        if self.principals.is_empty() || self.principals.len() > MAX_PRINCIPALS {
            return Err(IngressError::new(
                ErrorCode::ManifestInvalid,
                format!(
                    "principal count {} is outside 1..={MAX_PRINCIPALS}",
                    self.principals.len()
                ),
            ));
        }

        let mut principal_ids = HashSet::new();
        let mut entity_ids = HashSet::new();
        let mut fingerprints = HashSet::new();
        let mut total_grants = 0usize;
        for principal in &self.principals {
            if !ncp_core::valid_id_segment(&principal.principal_id)
                || !ncp_core::valid_id_segment(&principal.entity_id)
            {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    "principal_id and entity_id must be canonical NCP identity segments",
                ));
            }
            if !principal_ids.insert(principal.principal_id.as_str())
                || !entity_ids.insert(principal.entity_id.as_str())
                || !fingerprints.insert(principal.certificate_sha256.as_str())
            {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    "principal IDs, entity IDs, and certificate fingerprints must be unique",
                ));
            }
            if !closed_role(principal.role) {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    "unknown principal role cannot grant admission",
                ));
            }
            if !is_sha256_hex(&principal.certificate_sha256) {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    "certificate fingerprint is not lowercase SHA-256 hex",
                ));
            }
            if principal.grants.is_empty() || principal.grants.len() > MAX_GRANTS_PER_PRINCIPAL {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    format!(
                        "grant count is outside 1..={MAX_GRANTS_PER_PRINCIPAL} for one principal"
                    ),
                ));
            }
            total_grants = total_grants.saturating_add(principal.grants.len());
            if total_grants > MAX_TOTAL_GRANTS {
                return Err(IngressError::new(
                    ErrorCode::ManifestInvalid,
                    format!("total grant count exceeds {MAX_TOTAL_GRANTS}"),
                ));
            }
            let mut grants = Vec::new();
            for grant in &principal.grants {
                if !valid_literal(&grant.route, 256)
                    || !valid_literal(&grant.message_class, 64)
                    || !closed_plane(grant.plane)
                {
                    return Err(IngressError::new(
                        ErrorCode::ManifestInvalid,
                        "grant route, plane, or message class is empty, unknown, wildcarded, or unbounded",
                    ));
                }
                if grants.contains(&grant) {
                    return Err(IngressError::new(
                        ErrorCode::ManifestInvalid,
                        "duplicate route/plane/message-class grant",
                    ));
                }
                grants.push(grant);
            }
        }
        Ok(())
    }
}

/// Literal route, plane, and message class assigned by endpoint configuration.
#[derive(Clone, Debug)]
pub struct EndpointProfile {
    route: String,
    plane: Plane,
    message_class: String,
}

impl EndpointProfile {
    /// Constructs a closed, bounded endpoint profile.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] when a literal is empty, wildcarded, non-ASCII,
    /// unbounded, or the plane is unknown.
    pub fn new(
        route: impl Into<String>,
        plane: Plane,
        message_class: impl Into<String>,
    ) -> Result<Self, IngressError> {
        let route = route.into();
        let message_class = message_class.into();
        if !valid_literal(&route, 256) || !valid_literal(&message_class, 64) || !closed_plane(plane)
        {
            return Err(IngressError::new(
                ErrorCode::Configuration,
                "endpoint route, plane, and message class must be closed bounded literals",
            ));
        }
        Ok(Self {
            route,
            plane,
            message_class,
        })
    }
}

/// Result of publishing a valid manifest candidate.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RotationOutcome {
    /// A higher generation replaced the current immutable snapshot.
    Applied,
    /// Exact bytes at the current generation were republished idempotently.
    Unchanged,
}

/// Single-process immutable manifest publisher and snapshot source.
#[derive(Debug)]
pub struct ManifestStore {
    current: RwLock<Arc<ManifestSnapshot>>,
    boot_id: [u8; 16],
}

impl ManifestStore {
    /// Validates and installs the initial exact-byte manifest.
    ///
    /// A fresh random boot identifier distinguishes observations from separate
    /// store lifetimes. It is diagnostic only and is not persisted.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] on entropy failure or any manifest boundary
    /// violation.
    pub fn new(bytes: &[u8], expected_sha256: &str) -> Result<Self, IngressError> {
        let mut boot_id = [0u8; 16];
        getrandom::fill(&mut boot_id).map_err(|error| {
            IngressError::new(
                ErrorCode::Configuration,
                format!("cannot generate process-local manifest epoch: {error}"),
            )
        })?;
        Ok(Self {
            current: RwLock::new(Arc::new(ManifestSnapshot::parse(bytes, expected_sha256)?)),
            boot_id,
        })
    }

    /// Atomically publishes a valid higher-generation manifest.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] for invalid bytes, rollback, equivocation, or a
    /// poisoned writer lock.
    pub fn rotate(
        &self,
        bytes: &[u8],
        expected_sha256: &str,
    ) -> Result<RotationOutcome, IngressError> {
        let candidate = Arc::new(ManifestSnapshot::parse(bytes, expected_sha256)?);
        let mut current = self.current.write().map_err(|_| {
            IngressError::new(
                ErrorCode::ManifestInvalid,
                "manifest store lock is poisoned",
            )
        })?;
        if candidate.generation < current.generation {
            return Err(IngressError::new(
                ErrorCode::ManifestRollback,
                "manifest generation rollback rejected",
            ));
        }
        if candidate.generation == current.generation {
            if candidate.digest == current.digest {
                return Ok(RotationOutcome::Unchanged);
            }
            return Err(IngressError::new(
                ErrorCode::ManifestEquivocation,
                "same manifest generation has different exact bytes",
            ));
        }
        *current = candidate;
        Ok(RotationOutcome::Applied)
    }

    /// Returns the generation and exact-byte digest of one current snapshot.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] if the reader lock is poisoned.
    pub fn current_version(&self) -> Result<(u64, String), IngressError> {
        let current = self.snapshot()?;
        Ok((current.generation, current.digest.clone()))
    }

    fn snapshot(&self) -> Result<Arc<ManifestSnapshot>, IngressError> {
        self.current
            .read()
            .map(|value| Arc::clone(&value))
            .map_err(|_| {
                IngressError::new(
                    ErrorCode::ManifestInvalid,
                    "manifest store lock is poisoned",
                )
            })
    }

    fn early_deny_only(
        &self,
        leaf_sha256: &str,
        profile: &EndpointProfile,
    ) -> Result<(), IngressError> {
        if self.snapshot()?.permits(leaf_sha256, profile) {
            Ok(())
        } else {
            Err(IngressError::new(
                ErrorCode::ManifestDenied,
                "current manifest has no exact certificate/endpoint grant",
            ))
        }
    }

    fn decide_current(
        &self,
        leaf_sha256: &str,
        profile: &EndpointProfile,
        claim: &IdentityClaim,
        payload_sha256: String,
    ) -> Result<AuthenticatedContext, IngressError> {
        // Linearization point: this one snapshot load orders the complete
        // certificate/grant/claim decision relative to manifest rotations.
        let snapshot = self.snapshot()?;
        let entry = snapshot.entry_for_leaf(leaf_sha256).ok_or_else(|| {
            IngressError::new(
                ErrorCode::ManifestDenied,
                "certificate mapping was removed before final admission",
            )
        })?;
        if !snapshot.permits(leaf_sha256, profile) {
            return Err(IngressError::new(
                ErrorCode::ManifestDenied,
                "current manifest does not grant the exact endpoint profile",
            ));
        }
        if claim.principal_id != entry.principal_id
            || claim.entity_id != entry.entity_id
            || claim.role != entry.role
            || claim.plane != profile.plane
        {
            return Err(IngressError::new(
                ErrorCode::IdentityMismatch,
                "payload identity does not exactly match transport-bound manifest identity",
            ));
        }
        Ok(AuthenticatedContext {
            principal_id: entry.principal_id.clone(),
            entity_id: entry.entity_id.clone(),
            role: entry.role,
            plane: profile.plane,
            route: profile.route.clone(),
            message_class: profile.message_class.clone(),
            leaf_sha256: leaf_sha256.to_owned(),
            manifest_generation: snapshot.generation,
            manifest_sha256: snapshot.digest.clone(),
            boot_id: self.boot_id,
            payload_sha256,
        })
    }
}

/// Non-serializable diagnostic binding constructed only after final admission.
#[derive(Debug)]
pub struct AuthenticatedContext {
    principal_id: String,
    entity_id: String,
    role: PrincipalRole,
    plane: Plane,
    route: String,
    message_class: String,
    leaf_sha256: String,
    manifest_generation: u64,
    manifest_sha256: String,
    boot_id: [u8; 16],
    payload_sha256: String,
}

impl AuthenticatedContext {
    /// Returns the manifest-derived principal identifier.
    pub fn principal_id(&self) -> &str {
        &self.principal_id
    }

    /// Returns the manifest-derived entity identifier.
    pub fn entity_id(&self) -> &str {
        &self.entity_id
    }

    /// Returns the closed manifest-derived principal role.
    pub const fn role(&self) -> PrincipalRole {
        self.role
    }

    /// Returns the endpoint-pinned plane.
    pub const fn plane(&self) -> Plane {
        self.plane
    }

    /// Returns the endpoint-pinned literal route.
    pub fn route(&self) -> &str {
        &self.route
    }

    /// Returns the endpoint-pinned NCP message class.
    pub fn message_class(&self) -> &str {
        &self.message_class
    }

    /// Returns SHA-256 of the exact verified client leaf DER.
    pub fn leaf_sha256(&self) -> &str {
        &self.leaf_sha256
    }

    /// Returns the manifest generation used at the admission linearization point.
    pub const fn manifest_generation(&self) -> u64 {
        self.manifest_generation
    }

    /// Returns SHA-256 of the exact manifest bytes used for admission.
    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }

    /// Returns the process-local manifest-store epoch identifier.
    pub const fn boot_id(&self) -> &[u8; 16] {
        &self.boot_id
    }

    /// Returns SHA-256 of the exact immutable payload bytes.
    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }
}

/// Affine pair of one admitted context and the exact immutable payload bytes.
pub struct AuthenticatedMessage {
    context: AuthenticatedContext,
    payload: Box<[u8]>,
}

impl Debug for AuthenticatedMessage {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("AuthenticatedMessage")
            .field("context", &self.context)
            .field("payload_bytes", &self.payload.len())
            .field("payload_sha256", &self.context.payload_sha256)
            .finish()
    }
}

impl AuthenticatedMessage {
    /// Borrows the diagnostic authentication context without detaching it.
    pub fn context(&self) -> &AuthenticatedContext {
        &self.context
    }

    /// Borrows the exact received payload bytes without mutation.
    pub fn payload(&self) -> &[u8] {
        &self.payload
    }

    /// Returns the digest computed from the exact received payload at construction.
    pub fn payload_sha256(&self) -> &str {
        &self.context.payload_sha256
    }
}

/// Fixed resource and deadline bounds for one accepted connection.
#[derive(Clone, Copy, Debug)]
pub struct IngressLimits {
    /// Maximum time to accept TCP and complete the TLS handshake.
    pub handshake_timeout: Duration,
    /// Maximum time to read one complete frame and TLS closure.
    pub frame_timeout: Duration,
    /// Maximum application payload bytes, capped by the NCP frame limit.
    pub max_frame_bytes: usize,
}

impl Default for IngressLimits {
    fn default() -> Self {
        Self {
            handshake_timeout: Duration::from_secs(3),
            frame_timeout: Duration::from_secs(3),
            max_frame_bytes: ncp_core::bounded_json::MAX_FRAME_BYTES,
        }
    }
}

/// Loopback-only, one-frame TLS 1.3 terminating ingress.
#[derive(Debug)]
pub struct TlsIngress {
    tls_config: Arc<ServerConfig>,
    manifests: Arc<ManifestStore>,
    profile: EndpointProfile,
    limits: IngressLimits,
}

impl TlsIngress {
    /// Combines an opaque pinned TLS profile, manifest store, endpoint profile,
    /// and resource bounds.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] when the resource limits are zero or exceed the
    /// NCP bounded-JSON frame limit.
    pub fn new(
        tls_config: PinnedTls13ServerConfig,
        manifests: Arc<ManifestStore>,
        profile: EndpointProfile,
        limits: IngressLimits,
    ) -> Result<Self, IngressError> {
        if limits.handshake_timeout.is_zero()
            || limits.frame_timeout.is_zero()
            || limits.max_frame_bytes == 0
            || limits.max_frame_bytes > ncp_core::bounded_json::MAX_FRAME_BYTES
        {
            return Err(IngressError::new(
                ErrorCode::Configuration,
                "timeouts and frame limit must be positive and within the NCP frame bound",
            ));
        }
        Ok(Self {
            tls_config: tls_config.0,
            manifests,
            profile,
            limits,
        })
    }

    /// Accepts and processes exactly one loopback connection.
    ///
    /// # Errors
    ///
    /// Returns [`IngressError`] for any transport, TLS, manifest, framing,
    /// payload, identity, deadline, or resource-bound failure.
    pub async fn accept_one(
        &self,
        listener: &TcpListener,
    ) -> Result<AuthenticatedMessage, IngressError> {
        let local = listener.local_addr().map_err(|error| {
            IngressError::new(
                ErrorCode::Transport,
                format!("cannot inspect listener address: {error}"),
            )
        })?;
        if !local.ip().is_loopback() {
            return Err(IngressError::new(
                ErrorCode::Transport,
                "prototype listener is not loopback",
            ));
        }
        let (stream, peer) = timeout(self.limits.handshake_timeout, listener.accept())
            .await
            .map_err(|_| IngressError::new(ErrorCode::Timeout, "TCP accept timed out"))?
            .map_err(|error| {
                IngressError::new(ErrorCode::Transport, format!("TCP accept failed: {error}"))
            })?;
        if !peer.ip().is_loopback() {
            return Err(IngressError::new(
                ErrorCode::Transport,
                "prototype rejected a non-loopback peer",
            ));
        }
        self.accept_stream(stream).await
    }

    async fn accept_stream(&self, stream: TcpStream) -> Result<AuthenticatedMessage, IngressError> {
        ensure_loopback_stream(&stream)?;
        let acceptor = TlsAcceptor::from(Arc::clone(&self.tls_config));
        let mut tls = timeout(self.limits.handshake_timeout, acceptor.accept(stream))
            .await
            .map_err(|_| IngressError::new(ErrorCode::Timeout, "TLS handshake timed out"))?
            .map_err(|error| {
                IngressError::new(ErrorCode::Tls, format!("TLS handshake failed: {error}"))
            })?;
        let connection = tls.get_ref().1;
        if connection.protocol_version() != Some(rustls::ProtocolVersion::TLSv1_3) {
            return Err(IngressError::new(
                ErrorCode::Protocol,
                "negotiated protocol is not TLS 1.3",
            ));
        }
        if !matches!(
            connection.handshake_kind(),
            Some(rustls::HandshakeKind::Full)
                | Some(rustls::HandshakeKind::FullWithHelloRetryRequest)
        ) {
            return Err(IngressError::new(
                ErrorCode::Protocol,
                "resumed or indeterminate TLS handshakes are forbidden",
            ));
        }
        if connection.alpn_protocol() != Some(ALPN_PROTOCOL) {
            return Err(IngressError::new(
                ErrorCode::Protocol,
                "negotiated ALPN is not the one pinned prototype protocol",
            ));
        }
        let certificates = connection.peer_certificates().ok_or_else(|| {
            IngressError::new(
                ErrorCode::Tls,
                "verified TLS connection has no client certificate chain",
            )
        })?;
        let leaf = certificates.first().ok_or_else(|| {
            IngressError::new(ErrorCode::Tls, "client certificate chain is empty")
        })?;
        let leaf_sha256 = sha256_hex(leaf.as_ref());

        // This early lookup is intentionally deny-only. It prevents allocating a
        // payload for an obvious miss but cannot produce a context.
        self.manifests
            .early_deny_only(&leaf_sha256, &self.profile)?;

        let payload = read_one_frame(
            &mut tls,
            self.limits.frame_timeout,
            self.limits.max_frame_bytes,
        )
        .await?;
        let claim = validate_payload(&payload, &self.profile)?;
        let payload_sha256 = sha256_hex(&payload);
        let context =
            self.manifests
                .decide_current(&leaf_sha256, &self.profile, &claim, payload_sha256)?;
        Ok(AuthenticatedMessage {
            context,
            payload: payload.into_boxed_slice(),
        })
    }
}

fn ensure_loopback_stream(stream: &TcpStream) -> Result<(), IngressError> {
    let local = stream.local_addr().map_err(|error| {
        IngressError::new(
            ErrorCode::Transport,
            format!("cannot inspect local stream address: {error}"),
        )
    })?;
    let peer = stream.peer_addr().map_err(|error| {
        IngressError::new(
            ErrorCode::Transport,
            format!("cannot inspect peer stream address: {error}"),
        )
    })?;
    if !matches!(local.ip(), IpAddr::V4(_) | IpAddr::V6(_))
        || !local.ip().is_loopback()
        || !peer.ip().is_loopback()
    {
        return Err(IngressError::new(
            ErrorCode::Transport,
            "prototype TLS stream must be loopback on both ends",
        ));
    }
    Ok(())
}

async fn read_one_frame<S>(
    stream: &mut S,
    frame_timeout: Duration,
    max_frame_bytes: usize,
) -> Result<Vec<u8>, IngressError>
where
    S: tokio::io::AsyncRead + Unpin,
{
    timeout(frame_timeout, async {
        let mut prefix = [0u8; 4];
        stream.read_exact(&mut prefix).await.map_err(|error| {
            IngressError::new(
                ErrorCode::FrameIncomplete,
                format!("frame length prefix is incomplete: {error}"),
            )
        })?;
        let length = u32::from_be_bytes(prefix) as usize;
        if length == 0 || length > max_frame_bytes {
            return Err(IngressError::new(
                ErrorCode::FrameBounds,
                format!("frame length {length} is outside 1..={max_frame_bytes}"),
            ));
        }
        let mut payload = vec![0u8; length];
        stream.read_exact(&mut payload).await.map_err(|error| {
            IngressError::new(
                ErrorCode::FrameIncomplete,
                format!("frame body is incomplete: {error}"),
            )
        })?;
        let mut trailing = [0u8; 1];
        let count = stream.read(&mut trailing).await.map_err(|error| {
            IngressError::new(
                ErrorCode::FrameIncomplete,
                format!("TLS close boundary is incomplete: {error}"),
            )
        })?;
        if count != 0 {
            return Err(IngressError::new(
                ErrorCode::FrameTrailing,
                "second frame or trailing application byte rejected",
            ));
        }
        Ok(payload)
    })
    .await
    .map_err(|_| IngressError::new(ErrorCode::Timeout, "bounded frame read timed out"))?
}

fn validate_payload(
    payload: &[u8],
    profile: &EndpointProfile,
) -> Result<IdentityClaim, IngressError> {
    let value = ncp_core::bounded_json::parse_value(payload).map_err(|error| {
        IngressError::new(
            ErrorCode::PayloadInvalid,
            format!("payload bounded-JSON validation failed: {error}"),
        )
    })?;
    ncp_core::messages::validate(&value).map_err(|error| {
        IngressError::new(
            ErrorCode::PayloadInvalid,
            format!("payload is not a valid NCP message: {error}"),
        )
    })?;
    if ncp_core::messages::message_kind(&value) != Some(profile.message_class.as_str()) {
        return Err(IngressError::new(
            ErrorCode::IdentityMismatch,
            "payload message kind does not match the endpoint profile",
        ));
    }
    let identity = value
        .as_object()
        .and_then(|object| object.get("identity"))
        .ok_or_else(|| {
            IngressError::new(
                ErrorCode::IdentityMismatch,
                "payload has no identity claim at the profiled location",
            )
        })?;
    exact_identity_shape(identity)?;
    let claim: IdentityClaim = serde_json::from_value(identity.clone()).map_err(|error| {
        IngressError::new(
            ErrorCode::IdentityMismatch,
            format!("payload identity shape is invalid: {error}"),
        )
    })?;
    if claim.plane != profile.plane || !closed_role(claim.role) {
        return Err(IngressError::new(
            ErrorCode::IdentityMismatch,
            "payload identity plane or role is not closed and endpoint-congruent",
        ));
    }
    Ok(claim)
}

fn exact_identity_shape(identity: &Value) -> Result<(), IngressError> {
    let object = identity.as_object().ok_or_else(|| {
        IngressError::new(
            ErrorCode::IdentityMismatch,
            "payload identity is not an object",
        )
    })?;
    let expected = ["entity_id", "plane", "principal_id", "role"];
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err(IngressError::new(
            ErrorCode::IdentityMismatch,
            "payload identity must have exactly principal_id, entity_id, role, and plane",
        ));
    }
    Ok(())
}

/// Opaque proof that the server configuration came from the exact pinned builder.
pub struct PinnedTls13ServerConfig(Arc<ServerConfig>);

/// Builds the sole accepted TLS 1.3 mutual-authentication server profile.
///
/// The configuration pins ring, TLS 1.3, mandatory initial client-certificate
/// verification, one ALPN, no server session storage, no tickets, no early data,
/// no half-RTT data, and no secret extraction.
///
/// # Errors
///
/// Returns [`IngressError`] when roots, certificate material, protocol versions,
/// or a pinned postcondition are invalid.
pub fn build_tls13_server_config(
    client_roots: RootCertStore,
    server_chain: Vec<CertificateDer<'static>>,
    server_key: PrivateKeyDer<'static>,
) -> Result<PinnedTls13ServerConfig, IngressError> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let verifier =
        WebPkiClientVerifier::builder_with_provider(Arc::new(client_roots), Arc::clone(&provider))
            .build()
            .map_err(|error| {
                IngressError::new(
                    ErrorCode::Configuration,
                    format!("cannot build mandatory client-certificate verifier: {error}"),
                )
            })?;
    let mut config = ServerConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&version::TLS13])
        .map_err(|error| {
            IngressError::new(
                ErrorCode::Configuration,
                format!("cannot pin TLS 1.3: {error}"),
            )
        })?
        .with_client_cert_verifier(verifier)
        .with_single_cert(server_chain, server_key)
        .map_err(|error| {
            IngressError::new(
                ErrorCode::Configuration,
                format!("cannot install server certificate: {error}"),
            )
        })?;
    config.alpn_protocols = vec![ALPN_PROTOCOL.to_vec()];
    config.session_storage = Arc::new(NoServerSessionStorage {});
    config.send_tls13_tickets = 0;
    config.max_early_data_size = 0;
    config.send_half_rtt_data = false;
    config.enable_secret_extraction = false;
    if config.alpn_protocols.as_slice() != [ALPN_PROTOCOL]
        || config.send_tls13_tickets != 0
        || config.max_early_data_size != 0
        || config.send_half_rtt_data
        || config.enable_secret_extraction
        || config.session_storage.can_cache()
    {
        return Err(IngressError::new(
            ErrorCode::Configuration,
            "constructed TLS profile did not preserve its pinned fail-closed invariants",
        ));
    }
    Ok(PinnedTls13ServerConfig(Arc::new(config)))
}

/// Diagnostic output from the disposable volatile duplicate detector.
#[derive(Debug, PartialEq, Eq)]
pub struct ReplayObservation {
    duplicate_exact_message: bool,
}

impl ReplayObservation {
    /// Returns whether the same principal and exact payload digest were seen.
    pub const fn duplicate_exact_message(&self) -> bool {
        self.duplicate_exact_message
    }
}

/// In-memory duplicate detector that is intentionally outside ingress admission.
#[derive(Debug, Default)]
pub struct VolatileReplayProbe {
    seen: HashSet<(String, String)>,
}

impl VolatileReplayProbe {
    /// Consumes one complete authenticated message and records its diagnostic key.
    ///
    /// Clearing or reconstructing this probe must never change ingress admission.
    ///
    /// # Errors
    ///
    /// This prototype currently has no fallible observation step; the result
    /// remains explicit so later bounded diagnostic failures cannot become
    /// implicit admission behavior.
    pub fn observe(
        &mut self,
        message: AuthenticatedMessage,
    ) -> Result<ReplayObservation, IngressError> {
        let key = (
            message.context.principal_id.clone(),
            message.context.payload_sha256.clone(),
        );
        Ok(ReplayObservation {
            duplicate_exact_message: !self.seen.insert(key),
        })
    }
}

#[cfg(test)]
mod compile_time_invariants {
    use super::{AuthenticatedContext, AuthenticatedMessage};
    use static_assertions::assert_not_impl_any;

    assert_not_impl_any!(
        AuthenticatedContext:
            Clone,
            Default,
            serde::Serialize,
            serde::de::DeserializeOwned
    );
    assert_not_impl_any!(
        AuthenticatedMessage:
            Clone,
            Default,
            serde::Serialize,
            serde::de::DeserializeOwned,
            AsRef<[u8]>
    );
}
