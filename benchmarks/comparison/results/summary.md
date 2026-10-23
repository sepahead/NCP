# Comparison benchmark: results

Protocol SHA-256 `e711a417841de8ef100dbc0a274f1e290d22c9da8295f0ce1cb794f21eb4f7a7`; 276 runs in 3 blocks, 2026-10-23T18:28:27.649112Z to 2026-10-23T18:37:13.647483Z UTC; failed runs that counted: 0.
One-minute load average before the runs: 2.78 to 5.3. Power source: Battery Power.

Statistic: the median of three block medians, in µs. Range: the smallest and largest block median.

## Rust client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 9.1 (9.0–9.2) | 14.0 (14.0–14.1) | 32.8 (32.7–32.8) | 902.6 (900.3–906.1) |
| NCP 2, pipe, no digest check | 9.0 (9.0–9.0) | 13.4 (13.2–13.4) | 24.1 (23.8–24.1) | 528.4 (527.4–531.2) |
| NCP 2, Unix socket | 9.6 (9.5–9.7) | 14.5 (14.3–15.5) | 33.2 (33.0–33.4) | 796.7 (792.3–816.1) |
| NCP 2, TCP | 24.5 (23.5–25.6) | 30.8 (30.7–31.4) | 50.0 (49.5–50.1) | 963.9 (961.6–964.5) |
| NCP 1.0.1, pipe | 37.9 (36.2–38.8) | 68.2 (66.2–68.4) | 417.4 (413.0–418.2) | not measured |
| gRPC (tonic), TCP | 46.9 (46.7–47.9) | 46.6 (45.9–47.6) | 54.0 (53.6–55.0) | 234.2 (231.1–237.8) |
| Zenoh, TCP | 57.8 (55.5–57.8) | 58.2 (57.5–59.7) | 62.7 (61.1–62.7) | 286.5 (284.3–302.9) |
| Raw pipe, no protocol | 4.5 (4.5–4.5) | 7.3 (7.2–7.3) | 8.1 (8.1–8.1) | 151.7 (151.3–151.7) |

## Python client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 38.6 (38.4–39.1) | 56.9 (48.0–64.6) | 67.8 (65.9–72.9) | 849.9 (846.7–852.5) |
| NCP 2, pipe, no digest check | 31.7 (31.5–37.0) | 54.5 (46.5–55.2) | 59.1 (58.1–63.9) | 551.7 (538.4–553.6) |
| NCP 2, Unix socket | 36.0 (34.4–38.5) | 53.8 (48.9–55.0) | 66.1 (66.0–70.7) | 756.3 (755.2–758.0) |
| NCP 2, TCP | 45.8 (44.0–53.3) | 60.3 (60.2–60.5) | 76.8 (76.0–76.8) | 863.6 (793.5–870.5) |
| NCP 1.0.1, pipe | 457.8 (456.2–468.0) | 1246.8 (1245.1–1247.5) | 11187.1 (11051.4–11188.6) | not measured |
| gRPC (grpcio), Unix socket | 113.4 (112.5–115.4) | 115.1 (113.3–115.7) | 169.0 (168.2–171.2) | 3603.1 (3556.6–3637.0) |
| gRPC (grpcio), TCP | 124.3 (123.7–124.5) | 126.5 (125.4–127.1) | 129.5 (128.0–129.9) | 243.0 (242.2–243.7) |
| ZeroMQ, ipc | 56.2 (55.6–56.8) | 56.2 (55.3–56.9) | 74.9 (73.0–77.4) | 1051.0 (1018.3–1069.8) |
| ZeroMQ, TCP | 63.0 (61.5–64.7) | 63.7 (63.3–65.0) | 86.9 (85.7–86.9) | 181.8 (179.6–183.1) |
| HTTP/1.1, TCP | 75.2 (75.2–75.2) | 76.3 (76.0–79.2) | 75.2 (74.9–79.5) | 143.7 (143.0–147.7) |
| Zenoh, TCP | 62.8 (62.6–63.2) | 64.2 (63.6–65.4) | 65.3 (65.0–66.7) | 147.9 (137.2–155.0) |
| Raw pipe, no protocol | 9.3 (9.2–9.5) | 9.3 (9.2–9.5) | 9.5 (9.4–10.5) | 188.9 (188.8–191.1) |

## Mixed languages over pipes

| Client, owner | N | NCP 2 | NCP 1.0.1 | Ratio |
| --- | ---: | ---: | ---: | ---: |
| Rust, Rust | 0 | 9.1 | 37.9 | 4.16 |
| Rust, Rust | 127 | 14.0 | 68.2 | 4.85 |
| Rust, Rust | 1788 | 32.8 | 417.4 | 12.7 |
| Rust, Python | 0 | 19.5 | 209.5 | 10.7 |
| Rust, Python | 127 | 25.7 | 670.3 | 26.1 |
| Rust, Python | 1788 | 40.7 | 6376.3 | 157 |
| Python, Rust | 0 | 19.6 | 240.3 | 12.2 |
| Python, Rust | 127 | 28.4 | 615.5 | 21.7 |
| Python, Rust | 1788 | 44.2 | 5283.3 | 120 |
| Python, Python | 0 | 38.6 | 457.8 | 11.9 |
| Python, Python | 127 | 56.9 | 1246.8 | 21.9 |
| Python, Python | 1788 | 67.8 | 11187.1 | 165 |

## Hypotheses

| # | Supported | Detail |
| --- | --- | --- |
| H1 | yes | 12 of 12 comparisons hold |
| H2 | yes | ncp2-rust-rust-pipe-n0: 9.1 µs (limit 15); ncp2-python-python-pipe-n0: 38.6 µs (limit 150); ncp2-python-python-pipe-n127: 56.9 µs (limit 150) |
| H3 | yes | 4.6 µs added (limit 10) |
| H4 | yes | 10 of 10 comparisons hold |
| H5 | yes | 9 of 9 comparisons hold |

## Where the time of an NCP 2 call goes, over pipes

| Language | N | Floor | Rest of NCP 2 | Digest comparison | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.5 | 4.5 | 0.1† | 9.1 |
| Rust | 127 | 7.3 | 6.1 | 0.7 | 14.0 |
| Rust | 1788 | 8.1 | 16.0 | 8.8 | 32.8 |
| Rust | 87381 | 151.7 | 376.7 | 374.2 | 902.6 |
| Python | 0 | 9.3 | 22.4 | 6.9 | 38.6 |
| Python | 127 | 9.3 | 45.1 | 2.4† | 56.9 |
| Python | 1788 | 9.5 | 49.6 | 8.7 | 67.8 |
| Python | 87381 | 188.9 | 362.8 | 298.2 | 849.9 |

† Smaller than the spread of the block medians of the two arms that give the part: variation between runs, not a measured cost.
