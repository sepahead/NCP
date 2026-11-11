# The Zenoh binding of NCP 2, for Python

`sepahead-ncp-zenoh` (module `ncp_zenoh`) carries NCP 2 frames as Zenoh queries, replies, and publications ([specification section 9.2](https://github.com/sepahead/NCP/blob/main/spec/NCP-2.md#92-zenoh-binding)).
It needs the NCP 2 core package `sepahead-ncp` and `eclipse-zenoh` 1.10.2.

- `ZenohChannel(session, service)`: a client channel for `ncp.Client`; it sends a request again when no reply arrives in time.
- `serve(session, service, make_owner)`: serve one owner for each session on `ncp/x/<service>`.
- `stream_sender(session, name)` and `subscribe(session, name, on_frame)`: streams on `ncp/s/<name>`.
- `secure_config(...)`: mutual TLS for networks that are not trusted; add Zenoh access control to it.

The [binding's README](https://github.com/sepahead/NCP/blob/main/bindings/zenoh/README.md) explains its behavior, security, tests, and limits.
NCP 2 is in development and not released.
