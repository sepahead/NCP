# Comparison benchmark: results of protocol 5

Protocol SHA-256 `50e735269a295242fbb812895484c0e4ca85f3b84ab5d5ac3719d5405d952047`; 420 runs in 3 blocks, 2026-11-19T01:11:47.318801Z to 2026-11-19T01:26:52.599081Z UTC; failed runs that counted: 0.
One-minute load average before the runs: 3.25 to 5.48. Power source: AC Power.
Disturbed attempts: 0; runs still disturbed after the last attempt: 0. Clock of a core before each run: 4.001 to 4.501 GHz; after it: 3.906 to 4.502 GHz. Waiting for the conditions: 4 minutes in all.

Statistic: the median of three block medians, in µs. Range: the smallest and largest block median.

## Rust client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 9.9 (9.7–10.1) | 15.2 (15.1–15.8) | 33.0 (33.0–33.0) | 901.3 (898.8–902.4) |
| NCP 2, pipe, no digest check | 9.7 (9.7–9.7) | 14.2 (14.1–14.3) | 24.5 (24.3–25.8) | 538.8 (538.1–541.1) |
| NCP 2, Unix socket | 11.0 (10.9–11.4) | 16.4 (16.1–17.0) | 34.2 (34.2–34.4) | 801.5 (800.0–807.0) |
| NCP 2, TCP | 26.8 (25.6–27.0) | 31.2 (30.7–31.2) | 52.0 (51.9–52.5) | 963.5 (950.2–965.3) |
| NCP 1.0.1, pipe | 38.2 (36.3–38.7) | 69.0 (68.7–69.3) | 429.8 (427.6–430.8) | not measured |
| gRPC (tonic), TCP | 46.3 (45.8–46.6) | 46.7 (46.2–46.7) | 53.4 (53.2–54.2) | 231.1 (230.2–232.8) |
| Zenoh, TCP | 56.7 (56.3–57.8) | 57.8 (57.3–59.1) | 62.2 (61.8–62.4) | 369.6 (364.5–379.7) |
| Raw pipe, no protocol | 4.5 (4.5–4.6) | 7.6 (5.5–7.7) | 8.4 (8.3–8.4) | 150.8 (142.8–151.2) |

## Python client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 52.4 (52.2–58.3) | 73.2 (72.7–73.4) | 84.1 (80.7–94.3) | 834.4 (833.4–838.7) |
| NCP 2, pipe, no digest check | 57.2 (51.7–57.2) | 68.8 (66.1–69.7) | 78.2 (77.4–80.6) | 535.5 (526.6–565.2) |
| NCP 2, Unix socket | 56.7 (56.6–58.6) | 66.5 (45.6–73.7) | 84.7 (81.4–86.8) | 740.2 (734.5–823.6) |
| NCP 2, TCP | 62.0 (60.0–62.0) | 75.4 (75.3–83.3) | 90.5 (89.4–95.7) | 881.9 (873.1–965.2) |
| NCP 1.0.1, pipe | 473.1 (469.8–477.0) | 1252.8 (1250.5–1259.7) | 11305.5 (11283.2–11465.3) | not measured |
| gRPC (grpcio), Unix socket | 112.1 (111.4–113.2) | 112.9 (112.1–113.3) | 166.6 (164.7–168.2) | 3609.1 (3473.5–3636.9) |
| gRPC (grpcio), TCP | 122.5 (122.4–123.4) | 124.7 (123.7–124.8) | 128.2 (127.2–131.2) | 241.2 (229.8–255.9) |
| ZeroMQ, ipc | 52.9 (52.5–53.3) | 55.0 (54.4–55.2) | 76.0 (71.9–78.3) | 1041.2 (993.0–1059.5) |
| ZeroMQ, TCP | 58.2 (57.8–59.7) | 59.4 (59.2–60.6) | 83.0 (82.5–84.5) | 178.2 (177.2–181.0) |
| HTTP/1.1, TCP | 75.2 (74.5–75.2) | 75.2 (75.2–76.2) | 74.2 (72.8–75.3) | 145.2 (142.5–146.2) |
| Zenoh, TCP | 62.8 (62.1–62.8) | 63.5 (63.2–63.7) | 66.0 (64.3–66.5) | 142.2 (140.8–156.2) |
| Raw pipe, no protocol | 9.4 (8.5–9.4) | 8.5 (8.5–9.4) | 10.0 (9.3–10.9) | 186.0 (185.0–186.9) |

## Rust: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (tonic), Unix socket | 34.7 (30.7–35.3) | 31.3 (27.3–32.4) | 55.8 (55.8–57.5) | 1173.9 (1168.5–1188.8) |
| gRPC (tonic), Unix socket + SHA-256 | 34.8 (34.7–35.9) | 34.7 (33.4–35.9) | 74.8 (70.8–76.3) | 1894.0 (1880.0–1910.6) |
| gRPC (tonic), TCP + SHA-256 | 45.4 (44.2–46.0) | 47.0 (46.5–49.2) | 73.2 (73.1–73.5) | 1122.5 (1121.0–1196.5) |
| Zenoh, TCP + SHA-256 | 57.4 (56.5–58.3) | 59.0 (58.8–59.8) | 80.2 (79.9–81.0) | 1109.7 (1099.8–1164.2) |
| Raw pipe + SHA-256 | 4.9 (4.9–5.2) | 9.0 (8.8–9.0) | 23.3 (23.0–27.0) | 869.8 (869.5–937.6) |

## Python: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (grpcio), Unix socket + SHA-256 | 115.8 (115.4–120.2) | 118.3 (118.1–119.0) | 185.8 (184.1–186.3) | 4207.6 (4175.0–4441.7) |
| gRPC (grpcio), TCP + SHA-256 | 126.5 (124.9–127.3) | 129.5 (128.5–129.8) | 147.8 (147.5–150.0) | 942.1 (942.1–1028.1) |
| ZeroMQ, ipc + SHA-256 | 57.4 (55.0–58.4) | 58.4 (57.3–58.6) | 97.1 (94.5–97.1) | 1634.2 (1623.8–1639.1) |
| ZeroMQ, TCP + SHA-256 | 64.0 (63.5–66.7) | 66.7 (64.5–67.6) | 104.7 (102.4–104.9) | 909.3 (907.3–910.8) |
| HTTP/1.1, TCP + SHA-256 | 78.8 (78.2–86.5) | 79.2 (79.2–79.7) | 89.0 (89.0–90.2) | 816.2 (815.8–906.1) |
| Zenoh, TCP + SHA-256 | 64.6 (64.6–68.5) | 66.8 (66.6–68.1) | 85.2 (84.9–86.1) | 780.4 (780.4–804.7) |
| Raw pipe + SHA-256 | 9.2 (9.0–11.5) | 10.2 (9.8–11.2) | 25.4 (25.4–30.1) | 798.8 (792.0–802.7) |

## Mixed languages over pipes

| Client, owner | N | NCP 2 | NCP 1.0.1 | Ratio |
| --- | ---: | ---: | ---: | ---: |
| Rust, Rust | 0 | 9.9 | 38.2 | 3.87 |
| Rust, Rust | 127 | 15.2 | 69.0 | 4.52 |
| Rust, Rust | 1788 | 33.0 | 429.8 | 13 |
| Rust, Python | 0 | 26.7 | 212.5 | 7.97 |
| Rust, Python | 127 | 30.6 | 677.3 | 22.1 |
| Rust, Python | 1788 | 49.5 | 6440.7 | 130 |
| Python, Rust | 0 | 25.3 | 248.9 | 9.82 |
| Python, Rust | 127 | 31.6 | 627.1 | 19.8 |
| Python, Rust | 1788 | 54.9 | 5252.0 | 95.7 |
| Python, Python | 0 | 52.4 | 473.1 | 9.03 |
| Python, Python | 127 | 73.2 | 1252.8 | 17.1 |
| Python, Python | 1788 | 84.1 | 11305.5 | 134 |

## Hypotheses

| # | Supported | Detail |
| --- | --- | --- |
| H1 | yes | 12 of 12 comparisons hold |
| H2 | yes | ncp2-rust-rust-pipe-n0: 9.9 µs (limit 15); ncp2-python-python-pipe-n0: 52.4 µs (limit 150); ncp2-python-python-pipe-n127: 73.2 µs (limit 150) |
| H3 | yes | 5.3 µs added (limit 10) |
| H4 | yes | 10 of 10 comparisons hold |
| H5 | no | 8 of 9 comparisons hold; ncp2-python-python-pipe-n1788 not below http-python-tcp-n1788 |
| R1 | no | 4 of H1 to H5 hold again: H1, H2, H3, H4 |
| R2 | yes | 9 of 9 comparisons hold |
| R3 | yes | 6 of 6 comparisons hold |

## Where the time of an NCP 2 call goes, over pipes

| Language | N | Floor | Rest of NCP 2 | Digest comparison | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.5 | 5.1 | 0.2† | 9.9 |
| Rust | 127 | 7.6 | 6.6 | 1.0 | 15.2 |
| Rust | 1788 | 8.4 | 16.0 | 8.5 | 33.0 |
| Rust | 87381 | 150.8 | 388.0 | 362.5 | 901.3 |
| Python | 0 | 9.4 | 47.8 | 0.0† (below zero: digest, drawn as zero) | 52.4 |
| Python | 127 | 8.5 | 60.2 | 4.5 | 73.2 |
| Python | 1788 | 10.0 | 68.2 | 5.9† | 84.1 |
| Python | 87381 | 186.0 | 349.5 | 298.9 | 834.4 |

† Smaller than the spread of the block medians of the two arms that give the part: variation between runs, not a measured cost.

## The integrity check alone, over pipes (exploratory)

Check: the raw pipe with SHA-256 at both ends minus the raw pipe. Rest of NCP 2: NCP 2 minus the raw pipe with SHA-256; below zero when NCP 2 is faster than the raw pipe with the same check.

| Language | N | Raw pipe | Check | Rest of NCP 2 | NCP 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.5 | 0.4 | 5.0 | 9.9 |
| Rust | 127 | 7.6 | 1.3 | 6.3 | 15.2 |
| Rust | 1788 | 8.4 | 14.9 | 9.7 | 33.0 |
| Rust | 87381 | 150.8 | 719.0 | 31.5 | 901.3 |
| Python | 0 | 9.4 | -0.2 | 43.2 | 52.4 |
| Python | 127 | 8.5 | 1.6 | 63.0 | 73.2 |
| Python | 1788 | 10.0 | 15.5 | 58.7 | 84.1 |
| Python | 87381 | 186.0 | 612.8 | 35.7 | 834.4 |
