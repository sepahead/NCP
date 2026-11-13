//! Events: what an owner, a client, or a server did, for logs and metrics.
//!
//! Give an [`Observer`] to an owner, a client, or a server. Without one, the SDK writes only the
//! errors that an operator must see, such as an error of the application, to standard error.

use std::fmt;
use std::sync::Arc;

/// One event. `kind` is one of: "opened", "open_rejected", "admitted", "repeated", "rejected",
/// "expired", "shutdown", "application_error", "session_end" (owner side); "sent", "resent",
/// "verdict", "ignored" (client side); "connection_refused", "server_error" (servers).
#[derive(Debug, Clone, Default)]
pub struct Event {
    /// What happened.
    pub kind: &'static str,
    /// "owner", "client", or "server".
    pub role: &'static str,
    /// The session, if known.
    pub session: Option<String>,
    /// The sequence number, if known.
    pub seq: Option<u64>,
    /// The operation, if known.
    pub op: Option<String>,
    /// The outcome of a response, if any.
    pub outcome: Option<&'static str>,
    /// The code of a response, if any.
    pub code: Option<String>,
    /// A description, for errors.
    pub detail: Option<String>,
    /// The error, as text.
    pub error: Option<String>,
}

/// Receives events.
pub trait Observer: Send + Sync {
    /// One event.
    fn event(&self, event: &Event);
}

impl fmt::Debug for dyn Observer {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Observer")
    }
}

/// Writes application and server errors to standard error, so that a failure never passes
/// silently. The default observer.
#[derive(Debug, Default, Clone, Copy)]
pub struct ErrorsToStderr;

impl Observer for ErrorsToStderr {
    fn event(&self, event: &Event) {
        if matches!(event.kind, "application_error" | "server_error") {
            eprintln!(
                "ncp {} {}: session {} seq {} op {}: {}{}",
                event.role,
                event.kind,
                event.session.as_deref().unwrap_or("-"),
                event.seq.map_or("-".to_owned(), |s| s.to_string()),
                event.op.as_deref().unwrap_or("-"),
                event.detail.as_deref().unwrap_or(""),
                event
                    .error
                    .as_deref()
                    .map_or(String::new(), |e| format!(": {e}")),
            );
        }
    }
}

/// Ignores every event.
#[derive(Debug, Default, Clone, Copy)]
pub struct Silent;

impl Observer for Silent {
    fn event(&self, _event: &Event) {}
}

/// The default observer.
pub fn default_observer() -> Arc<dyn Observer> {
    Arc::new(ErrorsToStderr)
}
