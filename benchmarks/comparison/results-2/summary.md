# Comparison benchmark: results of protocol 2

Protocol SHA-256 `1d7a7451760f1dcf42ef321cddd1c9baaee97a56c2d9123a44c0de43ebab7921`; 420 runs in 3 blocks, 2026-11-02T23:05:56.910725Z to 2026-11-02T23:18:44.006304Z UTC; failed runs that counted: 0.
One-minute load average before the runs: 2.25 to 4.01. Power source: AC Power.
Disturbed attempts: 0; runs still disturbed after the last attempt: 0. Clock of a core before each run: 4.027 to 4.506 GHz; after it: 4.076 to 4.505 GHz. Waiting for the conditions: 1 minute in all.

Statistic: the median of three block medians, in µs. Range: the smallest and largest block median.

## Rust client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 9.0 (9.0–9.1) | 13.9 (13.8–15.5) | 32.5 (32.5–32.6) | 918.2 (890.5–939.6) |
| NCP 2, pipe, no digest check | 9.0 (8.9–10.0) | 12.9 (12.9–13.2) | 23.7 (23.4–23.7) | 530.4 (527.7–555.8) |
| NCP 2, Unix socket | 9.5 (9.4–9.5) | 14.1 (14.0–15.6) | 33.0 (33.0–33.0) | 871.5 (865.9–875.0) |
| NCP 2, TCP | 27.0 (24.5–27.5) | 30.8 (30.6–32.7) | 51.1 (51.1–51.6) | 1013.3 (965.4–1025.1) |
| NCP 1.0.1, pipe | 36.1 (35.7–42.3) | 72.8 (66.0–73.0) | 430.1 (427.1–430.2) | not measured |
| gRPC (tonic), TCP | 47.9 (46.7–49.0) | 48.2 (47.7–48.9) | 54.7 (54.2–55.2) | 258.7 (256.5–259.7) |
| Zenoh, TCP | 59.5 (57.2–60.2) | 60.7 (60.5–61.0) | 63.5 (63.1–64.7) | 370.5 (369.5–379.7) |
| Raw pipe, no protocol | 4.5 (4.5–4.6) | 7.5 (7.5–7.6) | 8.4 (8.4–8.5) | 150.9 (149.3–150.9) |

## Python client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 38.8 (32.8–40.8) | 49.2 (48.6–55.8) | 67.2 (65.5–73.8) | 909.0 (900.8–910.5) |
| NCP 2, pipe, no digest check | 37.2 (32.0–39.2) | 47.9 (47.5–54.1) | 57.4 (57.2–64.6) | 565.2 (538.6–572.8) |
| NCP 2, Unix socket | 38.9 (32.9–39.0) | 57.2 (49.5–57.6) | 70.2 (65.6–85.6) | 759.2 (755.0–759.5) |
| NCP 2, TCP | 48.4 (42.6–48.8) | 59.8 (59.6–62.5) | 85.4 (74.3–87.4) | 920.5 (871.5–922.5) |
| NCP 1.0.1, pipe | 468.6 (459.4–472.8) | 1254.5 (1248.3–1262.5) | 11262.5 (11221.3–11288.2) | not measured |
| gRPC (grpcio), Unix socket | 114.5 (112.8–117.5) | 112.2 (111.3–112.6) | 171.4 (167.6–176.4) | 3772.4 (3710.4–3786.2) |
| gRPC (grpcio), TCP | 128.7 (127.4–133.0) | 128.7 (128.5–128.7) | 135.0 (132.7–135.9) | 244.4 (239.2–250.4) |
| ZeroMQ, ipc | 54.6 (52.3–56.4) | 56.0 (55.1–57.5) | 79.6 (78.2–81.3) | 1006.1 (963.8–1072.0) |
| ZeroMQ, TCP | 66.1 (63.7–66.7) | 67.0 (65.5–68.0) | 87.6 (86.9–90.0) | 181.6 (181.0–181.7) |
| HTTP/1.1, TCP | 80.3 (74.7–85.0) | 88.5 (85.2–88.6) | 74.7 (74.5–76.7) | 139.3 (136.3–145.6) |
| Zenoh, TCP | 65.2 (64.0–66.3) | 65.1 (64.8–66.3) | 68.9 (67.4–69.5) | 143.8 (142.7–145.6) |
| Raw pipe, no protocol | 9.2 (8.6–10.6) | 9.2 (8.5–9.2) | 11.7 (10.3–11.7) | 185.7 (181.5–185.9) |

## Rust: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (tonic), Unix socket | 35.9 (32.0–36.1) | 34.5 (32.0–35.6) | 55.6 (53.9–57.1) | 1199.9 (1185.0–1258.8) |
| gRPC (tonic), Unix socket + SHA-256 | 35.6 (32.0–35.9) | 35.2 (34.1–37.8) | 77.1 (76.2–78.3) | 1894.2 (1885.8–1915.5) |
| gRPC (tonic), TCP + SHA-256 | 48.2 (46.5–48.8) | 48.8 (47.2–49.4) | 75.3 (74.9–75.9) | 1136.8 (1128.7–1218.8) |
| Zenoh, TCP + SHA-256 | 60.4 (60.3–60.5) | 61.7 (61.0–62.2) | 84.8 (83.6–84.9) | 1104.1 (1091.4–1146.0) |
| Raw pipe + SHA-256 | 4.9 (4.8–5.0) | 9.0 (9.0–9.3) | 23.0 (22.9–23.1) | 873.4 (872.2–921.6) |

## Python: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (grpcio), Unix socket + SHA-256 | 116.0 (115.6–119.6) | 116.9 (116.5–117.7) | 185.3 (183.1–194.4) | 4215.2 (4103.2–4431.5) |
| gRPC (grpcio), TCP + SHA-256 | 131.6 (131.0–134.4) | 133.8 (133.1–137.4) | 149.2 (149.1–149.8) | 954.1 (952.6–1015.9) |
| ZeroMQ, ipc + SHA-256 | 59.3 (58.6–59.5) | 61.0 (60.6–61.2) | 99.8 (98.8–100.6) | 1683.4 (1613.7–1688.8) |
| ZeroMQ, TCP + SHA-256 | 66.7 (64.0–68.3) | 69.0 (69.0–71.2) | 105.0 (101.0–112.6) | 910.7 (909.1–920.4) |
| HTTP/1.1, TCP + SHA-256 | 78.5 (78.1–78.6) | 93.9 (93.9–94.3) | 90.6 (90.1–101.8) | 829.9 (825.9–887.3) |
| Zenoh, TCP + SHA-256 | 66.7 (65.6–66.9) | 70.0 (68.2–70.6) | 88.0 (86.4–89.9) | 801.2 (801.0–866.4) |
| Raw pipe + SHA-256 | 11.5 (8.5–11.6) | 12.5 (9.9–13.0) | 33.2 (25.1–33.3) | 801.8 (800.8–859.0) |

## Mixed languages over pipes

| Client, owner | N | NCP 2 | NCP 1.0.1 | Ratio |
| --- | ---: | ---: | ---: | ---: |
| Rust, Rust | 0 | 9.0 | 36.1 | 4.01 |
| Rust, Rust | 127 | 13.9 | 72.8 | 5.23 |
| Rust, Rust | 1788 | 32.5 | 430.1 | 13.2 |
| Rust, Python | 0 | 19.6 | 214.5 | 11 |
| Rust, Python | 127 | 28.2 | 669.8 | 23.7 |
| Rust, Python | 1788 | 48.0 | 6442.4 | 134 |
| Python, Rust | 0 | 19.2 | 245.9 | 12.8 |
| Python, Rust | 127 | 28.3 | 626.6 | 22.1 |
| Python, Rust | 1788 | 44.0 | 5271.2 | 120 |
| Python, Python | 0 | 38.8 | 468.6 | 12.1 |
| Python, Python | 127 | 49.2 | 1254.5 | 25.5 |
| Python, Python | 1788 | 67.2 | 11262.5 | 167 |

## Hypotheses

| # | Supported | Detail |
| --- | --- | --- |
| H1 | yes | 12 of 12 comparisons hold |
| H2 | yes | ncp2-rust-rust-pipe-n0: 9.0 µs (limit 15); ncp2-python-python-pipe-n0: 38.8 µs (limit 150); ncp2-python-python-pipe-n127: 49.2 µs (limit 150) |
| H3 | yes | 4.5 µs added (limit 10) |
| H4 | yes | 10 of 10 comparisons hold |
| H5 | yes | 9 of 9 comparisons hold |
| R1 | yes | 5 of H1 to H5 hold again: H1, H2, H3, H4, H5 |
| R2 | yes | 9 of 9 comparisons hold |
| R3 | yes | 6 of 6 comparisons hold |

## Where the time of an NCP 2 call goes, over pipes

| Language | N | Floor | Rest of NCP 2 | Digest comparison | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.5 | 4.5 | 0.0† (below zero: digest, drawn as zero) | 9.0 |
| Rust | 127 | 7.5 | 5.4 | 1.0† | 13.9 |
| Rust | 1788 | 8.4 | 15.3 | 8.8 | 32.5 |
| Rust | 87381 | 150.9 | 379.5 | 387.8 | 918.2 |
| Python | 0 | 9.2 | 28.0 | 1.6† | 38.8 |
| Python | 127 | 9.2 | 38.8 | 1.2† | 49.2 |
| Python | 1788 | 11.7 | 45.7 | 9.9 | 67.2 |
| Python | 87381 | 185.7 | 379.5 | 343.8 | 909.0 |

† Smaller than the spread of the block medians of the two arms that give the part: variation between runs, not a measured cost.

## The integrity check alone, over pipes (exploratory)

Check: the raw pipe with SHA-256 at both ends minus the raw pipe. Rest of NCP 2: NCP 2 minus the raw pipe with SHA-256; below zero when NCP 2 is faster than the raw pipe with the same check.

| Language | N | Raw pipe | Check | Rest of NCP 2 | NCP 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.5 | 0.4 | 4.1 | 9.0 |
| Rust | 127 | 7.5 | 1.5 | 4.9 | 13.9 |
| Rust | 1788 | 8.4 | 14.7 | 9.5 | 32.5 |
| Rust | 87381 | 150.9 | 722.5 | 44.8 | 918.2 |
| Python | 0 | 9.2 | 2.2 | 27.4 | 38.8 |
| Python | 127 | 9.2 | 3.4 | 36.6 | 49.2 |
| Python | 1788 | 11.7 | 21.5 | 34.0 | 67.2 |
| Python | 87381 | 185.7 | 616.2 | 107.1 | 909.0 |
