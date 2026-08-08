use std::fmt::{Display, Formatter};
use std::io;

#[derive(Debug)]
pub(crate) enum EngineError {
    Corpus(String),
    Input(String),
    Io { context: String, source: io::Error },
    Json(String),
    Semantic(String),
}

impl EngineError {
    pub(crate) fn corpus(detail: impl Into<String>) -> Self {
        Self::Corpus(detail.into())
    }

    pub(crate) fn input(detail: impl Into<String>) -> Self {
        Self::Input(detail.into())
    }

    pub(crate) fn io(context: impl Into<String>, source: io::Error) -> Self {
        Self::Io {
            context: context.into(),
            source,
        }
    }

    pub(crate) fn json(detail: impl Into<String>) -> Self {
        Self::Json(detail.into())
    }

    pub(crate) fn semantic(detail: impl Into<String>) -> Self {
        Self::Semantic(detail.into())
    }
}

impl Display for EngineError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Corpus(detail) => write!(formatter, "corpus: {detail}"),
            Self::Input(detail) => write!(formatter, "input: {detail}"),
            Self::Io { context, source } => write!(formatter, "I/O {context}: {source}"),
            Self::Json(detail) => write!(formatter, "JSON: {detail}"),
            Self::Semantic(detail) => write!(formatter, "semantic: {detail}"),
        }
    }
}

impl std::error::Error for EngineError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            Self::Corpus(_) | Self::Input(_) | Self::Json(_) | Self::Semantic(_) => None,
        }
    }
}

pub(crate) type EngineResult<T> = Result<T, EngineError>;
