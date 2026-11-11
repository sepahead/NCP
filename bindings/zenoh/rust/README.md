# The Zenoh binding of NCP 2, for Rust

`sepahead-ncp-zenoh` (library `ncp_zenoh`) carries NCP 2 frames as Zenoh queries, replies, and publications ([specification section 9.2](https://github.com/sepahead/NCP/blob/main/spec/NCP-2.md#92-zenoh-binding)).
It needs the NCP 2 core crate `sepahead-ncp-core` 2.x and Zenoh 1.10.2 or a later 1.x release, built with TCP and TLS links only; its tests use 1.10.2.

- `ZenohChannel::new(&session, service)`: a client channel for `ncp::Client`; it sends a request again when no reply arrives in time.
- `Server::declare(&session, service, make_owner, options)` and `Server::run`: one owner for each session on `ncp/x/<service>`.
- `StreamSender` and `subscribe`: streams on `ncp/s/<name>`.
- `secure_config(&TlsFiles, listen, connect)`: mutual TLS for networks that are not trusted; add Zenoh access control to it.

The [binding's README](https://github.com/sepahead/NCP/blob/main/bindings/zenoh/README.md) explains its behavior, security, tests, and limits.
Version 2.0.0, with NCP 2.0, which is prepared for release; the tag and the publication follow.
