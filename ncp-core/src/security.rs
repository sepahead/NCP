//! NCP 1.0 deployment-profile and authenticated-authority contract.
//!
//! Transport adapters obtain the cryptographic principal from their authenticated
//! connection. Payload identity never authenticates itself: [`AuthorityManifest`]
//! binds that transport identity to one principal, entity, role, and plane set.

pub use crate::messages::{IdentityClaim, Plane, PrincipalRole};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fmt;
use std::net::IpAddr;
use std::path::Path;

pub const DEV_LOOPBACK_INSECURE: &str = "dev-loopback-insecure";
pub const PRODUCTION_SECURE: &str = "production-secure";

pub const SECURITY_STATE_DIGEST_DOMAIN_V1: &[u8] = b"ncp.security-state-digest.v1\0";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "kebab-case", deny_unknown_fields)]
pub enum BindEndpoint {
    Tcp { host: String, port: u16 },
    Unix { path: String },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TlsFiles {
    pub ca_cert: String,
    pub peer_cert: String,
    pub private_key: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrincipalGrant {
    pub principal_id: String,
    pub certificate_identity: String,
    pub entity_id: String,
    pub role: PrincipalRole,
    #[serde(deserialize_with = "deserialize_unique_planes")]
    pub planes: BTreeSet<Plane>,
    #[serde(default)]
    pub may_reset_estop: bool,
    #[serde(default)]
    pub may_override: bool,
}

fn deserialize_unique_planes<'de, D>(deserializer: D) -> Result<BTreeSet<Plane>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let planes = Vec::<Plane>::deserialize(deserializer)?;
    let unique = planes.iter().copied().collect::<BTreeSet<_>>();
    if unique.len() != planes.len() {
        return Err(serde::de::Error::custom(
            "principal planes must not contain duplicates",
        ));
    }
    Ok(unique)
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorityManifest {
    pub realm: String,
    pub default_deny: bool,
    pub principals: Vec<PrincipalGrant>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentConfig {
    pub profile: String,
    pub bind: BindEndpoint,
    pub authority: AuthorityManifest,
    pub tls: Option<TlsFiles>,
    pub allow_downgrade: bool,
    pub insecure_status: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthenticatedActor {
    pub principal_id: String,
    pub certificate_identity: String,
    pub entity_id: String,
    pub role: PrincipalRole,
    pub may_reset_estop: bool,
    pub may_override: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SecurityError {
    pub code: &'static str,
    pub detail: String,
}

impl SecurityError {
    fn profile(detail: impl Into<String>) -> Self {
        Self {
            code: "NCP-PROFILE-001",
            detail: detail.into(),
        }
    }

    fn authorization(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SecurityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for SecurityError {}

fn valid_id(value: &str) -> bool {
    value.len() <= 128 && crate::keys::valid_id_segment(value)
}

fn endpoint_is_loopback(endpoint: &BindEndpoint) -> bool {
    match endpoint {
        BindEndpoint::Unix { path } => Path::new(path).is_absolute(),
        BindEndpoint::Tcp { host, .. } => host
            .parse::<IpAddr>()
            .is_ok_and(|address| address.is_loopback()),
    }
}

fn validate_endpoint(endpoint: &BindEndpoint) -> Result<(), SecurityError> {
    match endpoint {
        BindEndpoint::Tcp { host, port } => {
            if *port == 0
                || host.is_empty()
                || host.len() > 253
                || host
                    .chars()
                    .any(|character| character.is_control() || character.is_whitespace())
            {
                return Err(SecurityError::profile(
                    "TCP bind requires a bounded host and port in 1..65535",
                ));
            }
        }
        BindEndpoint::Unix { path } => {
            if !Path::new(path).is_absolute() {
                return Err(SecurityError::profile("Unix bind path must be absolute"));
            }
        }
    }
    Ok(())
}

impl AuthorityManifest {
    pub fn validate(&self) -> Result<(), SecurityError> {
        if !crate::keys::valid_realm(&self.realm) {
            return Err(SecurityError::profile(
                "authority realm is not a canonical NCP realm",
            ));
        }
        if !self.default_deny {
            return Err(SecurityError::profile(
                "authority manifest must be default-deny",
            ));
        }
        if self.principals.is_empty() {
            return Err(SecurityError::profile(
                "authority manifest has no principals",
            ));
        }
        let mut principal_ids = BTreeSet::new();
        let mut certificate_ids = BTreeSet::new();
        for grant in &self.principals {
            for (label, value) in [
                ("principal_id", grant.principal_id.as_str()),
                ("certificate_identity", grant.certificate_identity.as_str()),
                ("entity_id", grant.entity_id.as_str()),
            ] {
                if !valid_id(value) {
                    return Err(SecurityError::profile(format!(
                        "principal {label} {value:?} is empty, wildcarded, or not bounded"
                    )));
                }
            }
            if !principal_ids.insert(grant.principal_id.as_str()) {
                return Err(SecurityError::profile(format!(
                    "duplicate principal_id {:?}",
                    grant.principal_id
                )));
            }
            if !certificate_ids.insert(grant.certificate_identity.as_str()) {
                return Err(SecurityError::profile(format!(
                    "certificate identity {:?} maps to more than one principal",
                    grant.certificate_identity
                )));
            }
            if grant.planes.is_empty() {
                return Err(SecurityError::profile(format!(
                    "principal {:?} has no authorized planes",
                    grant.principal_id
                )));
            }
            if grant.role == PrincipalRole::Unknown || grant.planes.contains(&Plane::Unknown) {
                return Err(SecurityError::profile(format!(
                    "principal {:?} carries an unknown role or plane",
                    grant.principal_id
                )));
            }
            if grant.planes.contains(&Plane::Action)
                && !matches!(
                    grant.role,
                    PrincipalRole::Commander | PrincipalRole::Operator
                )
            {
                return Err(SecurityError::profile(format!(
                    "principal {:?} has action authority but role {:?}",
                    grant.principal_id, grant.role
                )));
            }
            if grant.may_reset_estop && grant.role != PrincipalRole::Operator {
                return Err(SecurityError::profile(format!(
                    "principal {:?} may reset ESTOP but is not an operator",
                    grant.principal_id
                )));
            }
            if grant.may_override && grant.role != PrincipalRole::Operator {
                return Err(SecurityError::profile(format!(
                    "principal {:?} may override authority but is not an operator",
                    grant.principal_id
                )));
            }
        }
        Ok(())
    }

    pub fn authenticate(
        &self,
        certificate_identity: &str,
        claimed_principal: &str,
        claimed_entity: &str,
        plane: Plane,
    ) -> Result<AuthenticatedActor, SecurityError> {
        let grant = self
            .principals
            .iter()
            .find(|grant| grant.certificate_identity == certificate_identity)
            .ok_or_else(|| {
                SecurityError::authorization("NCP-AUTH-001", "certificate identity is not enrolled")
            })?;
        if grant.principal_id != claimed_principal || grant.entity_id != claimed_entity {
            return Err(SecurityError::authorization(
                "NCP-AUTH-002",
                "authenticated principal/entity does not match the envelope claim",
            ));
        }
        if !grant.planes.contains(&plane) {
            return Err(SecurityError::authorization(
                "NCP-AUTH-003",
                "principal is not authorized for the requested plane",
            ));
        }
        Ok(AuthenticatedActor {
            principal_id: grant.principal_id.clone(),
            certificate_identity: grant.certificate_identity.clone(),
            entity_id: grant.entity_id.clone(),
            role: grant.role,
            may_reset_estop: grant.may_reset_estop,
            may_override: grant.may_override,
        })
    }

    /// Bind a complete payload claim to the cryptographic transport identity and
    /// the plane selected by the transport adapter.
    pub fn authenticate_claim(
        &self,
        certificate_identity: &str,
        claim: &IdentityClaim,
        expected_plane: Plane,
    ) -> Result<AuthenticatedActor, SecurityError> {
        if claim.plane != expected_plane || claim.role == PrincipalRole::Unknown {
            return Err(SecurityError::authorization(
                "NCP-AUTH-003",
                "payload plane/role claim does not match the transport boundary",
            ));
        }
        let actor = self.authenticate(
            certificate_identity,
            &claim.principal_id,
            &claim.entity_id,
            claim.plane,
        )?;
        if actor.role != claim.role {
            return Err(SecurityError::authorization(
                "NCP-AUTH-002",
                "payload role does not match the enrolled principal role",
            ));
        }
        Ok(actor)
    }
}

impl DeploymentConfig {
    pub fn validate(&self) -> Result<(), SecurityError> {
        self.authority.validate()?;
        validate_endpoint(&self.bind)?;
        if self.allow_downgrade {
            return Err(SecurityError::profile("security downgrade is forbidden"));
        }
        match self.profile.as_str() {
            DEV_LOOPBACK_INSECURE => {
                if !endpoint_is_loopback(&self.bind) {
                    return Err(SecurityError::profile(
                        "dev-loopback-insecure may bind only loopback or an absolute UDS path",
                    ));
                }
                if self.tls.is_some() {
                    return Err(SecurityError::profile(
                        "dev-loopback-insecure must not carry a partial TLS configuration",
                    ));
                }
                if !self.insecure_status {
                    return Err(SecurityError::profile(
                        "dev-loopback-insecure must emit an explicit insecure status",
                    ));
                }
            }
            PRODUCTION_SECURE => {
                if self.insecure_status {
                    return Err(SecurityError::profile(
                        "production-secure cannot advertise insecure status",
                    ));
                }
                let tls = self.tls.as_ref().ok_or_else(|| {
                    SecurityError::profile(
                        "production-secure requires CA, peer cert, and private key",
                    )
                })?;
                for (label, path) in [
                    ("ca_cert", tls.ca_cert.as_str()),
                    ("peer_cert", tls.peer_cert.as_str()),
                    ("private_key", tls.private_key.as_str()),
                ] {
                    if !Path::new(path).is_absolute() {
                        return Err(SecurityError::profile(format!(
                            "production-secure {label} path must be absolute"
                        )));
                    }
                }
            }
            other => {
                return Err(SecurityError::profile(format!(
                    "unknown deployment profile {other:?}"
                )))
            }
        }
        Ok(())
    }

    /// Portable content digest of the validated effective security policy.
    /// Certificate/key paths are covered; private key bytes are never read,
    /// serialized, or logged. Principal and plane order are semantically
    /// normalized before the domain-separated typed projection is hashed.
    pub fn security_state_digest(&self) -> Result<String, SecurityError> {
        self.validate()?;
        let mut principals = self.authority.principals.clone();
        principals.sort_by(|left, right| left.principal_id.cmp(&right.principal_id));
        let principals = principals
            .iter()
            .map(|grant| {
                let mut planes = grant
                    .planes
                    .iter()
                    .map(|plane| {
                        serde_json::to_value(plane)
                            .expect("registered Plane serializes")
                            .as_str()
                            .expect("Plane serializes as a string")
                            .to_owned()
                    })
                    .collect::<Vec<_>>();
                planes.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
                serde_json::json!({
                    "principal_id": grant.principal_id,
                    "certificate_identity": grant.certificate_identity,
                    "entity_id": grant.entity_id,
                    "role": grant.role,
                    "planes": planes,
                    "may_reset_estop": grant.may_reset_estop,
                    "may_override": grant.may_override,
                })
            })
            .collect::<Vec<_>>();
        let value = serde_json::json!({
            "profile": self.profile,
            "bind": self.bind,
            "authority": {
                "realm": self.authority.realm,
                "default_deny": self.authority.default_deny,
                "principals": principals,
            },
            "tls": self.tls,
            "allow_downgrade": self.allow_downgrade,
            "insecure_status": self.insecure_status,
        });
        let bytes =
            crate::canonical_digest::canonical_projection(SECURITY_STATE_DIGEST_DOMAIN_V1, &value)
                .map_err(|error| {
                    SecurityError::profile(format!("cannot canonicalize policy: {error}"))
                })?;
        Ok(crate::canonical_digest::sha256_hex(&bytes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest() -> AuthorityManifest {
        AuthorityManifest {
            realm: "ncp".into(),
            default_deny: true,
            principals: vec![PrincipalGrant {
                principal_id: "commander-1".into(),
                certificate_identity: "spiffe:ncp:commander-1".into(),
                entity_id: "brain-1".into(),
                role: PrincipalRole::Commander,
                planes: [Plane::Control, Plane::Action].into_iter().collect(),
                may_reset_estop: false,
                may_override: false,
            }],
        }
    }

    #[test]
    fn insecure_profile_is_loopback_only_and_unmistakable() {
        let mut config = DeploymentConfig {
            profile: DEV_LOOPBACK_INSECURE.into(),
            bind: BindEndpoint::Tcp {
                host: "127.0.0.1".into(),
                port: 7447,
            },
            authority: manifest(),
            tls: None,
            allow_downgrade: false,
            insecure_status: true,
        };
        assert!(config.validate().is_ok());
        config.bind = BindEndpoint::Tcp {
            host: "0.0.0.0".into(),
            port: 7447,
        };
        assert_eq!(config.validate().unwrap_err().code, "NCP-PROFILE-001");
    }

    #[test]
    fn production_profile_rejects_partial_tls_wildcards_and_downgrade() {
        let mut config = DeploymentConfig {
            profile: PRODUCTION_SECURE.into(),
            bind: BindEndpoint::Tcp {
                host: "0.0.0.0".into(),
                port: 7447,
            },
            authority: manifest(),
            tls: None,
            allow_downgrade: false,
            insecure_status: false,
        };
        assert!(config.validate().is_err());
        config.tls = Some(TlsFiles {
            ca_cert: "/run/ncp/ca.pem".into(),
            peer_cert: "/run/ncp/peer.pem".into(),
            private_key: "/run/ncp/peer.key".into(),
        });
        assert!(config.validate().is_ok());
        config.allow_downgrade = true;
        assert!(config.validate().is_err());
        config.allow_downgrade = false;
        config.authority.principals[0].entity_id = "*".into();
        assert!(config.validate().is_err());
    }

    #[test]
    fn authenticated_identity_is_bound_to_principal_entity_and_plane() {
        let manifest = manifest();
        let actor = manifest
            .authenticate(
                "spiffe:ncp:commander-1",
                "commander-1",
                "brain-1",
                Plane::Action,
            )
            .unwrap();
        assert_eq!(actor.role, PrincipalRole::Commander);
        assert_eq!(
            manifest
                .authenticate(
                    "spiffe:ncp:commander-1",
                    "commander-1",
                    "sibling",
                    Plane::Action,
                )
                .unwrap_err()
                .code,
            "NCP-AUTH-002"
        );
        assert_eq!(
            manifest
                .authenticate(
                    "spiffe:ncp:commander-1",
                    "commander-1",
                    "brain-1",
                    Plane::Perception,
                )
                .unwrap_err()
                .code,
            "NCP-AUTH-003"
        );
    }

    #[test]
    fn digest_is_order_normalized_and_secret_free() {
        let config = DeploymentConfig {
            profile: PRODUCTION_SECURE.into(),
            bind: BindEndpoint::Tcp {
                host: "0.0.0.0".into(),
                port: 7447,
            },
            authority: manifest(),
            tls: Some(TlsFiles {
                ca_cert: "/run/ncp/ca.pem".into(),
                peer_cert: "/run/ncp/peer.pem".into(),
                private_key: "/run/ncp/peer.key".into(),
            }),
            allow_downgrade: false,
            insecure_status: false,
        };
        let digest = config.security_state_digest().unwrap();
        assert_eq!(digest.len(), 64);
        assert!(digest
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f')));
    }
}
