# Comparison benchmark: results of protocol 3

Protocol SHA-256 `d1ddda6bdb6cc278d1223b222bd9d9a1a3b519cabba87c8791198f6605aba3db`; 420 runs in 3 blocks, 2026-11-18T19:04:44.120888Z to 2026-11-18T19:51:12.643659Z UTC; failed runs that counted: 0.
One-minute load average before the runs: 3.09 to 7.83. Power source: Battery Power.
Disturbed attempts: 0; runs still disturbed after the last attempt: 0. Clock of a core before each run: 4.0 to 4.488 GHz; after it: 3.854 to 4.488 GHz. Waiting for the conditions: 37 minutes in all.

Statistic: the median of three block medians, in µs. Range: the smallest and largest block median.

## Rust client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 11.0 (10.9–11.0) | 17.2 (17.1–17.2) | 36.1 (35.9–36.2) | 939.5 (911.4–942.1) |
| NCP 2, pipe, no digest check | 10.6 (10.2–10.9) | 16.2 (16.1–16.4) | 25.2 (24.6–26.3) | 560.6 (543.1–570.1) |
| NCP 2, Unix socket | 12.2 (11.1–12.5) | 18.4 (17.9–18.5) | 37.2 (35.2–37.7) | 895.1 (880.3–920.3) |
| NCP 2, TCP | 25.6 (25.5–25.8) | 31.9 (31.8–32.2) | 51.5 (45.0–52.0) | 1040.7 (987.4–1074.3) |
| NCP 1.0.1, pipe | 41.0 (38.9–43.2) | 73.3 (63.8–77.4) | 433.7 (433.6–440.2) | not measured |
| gRPC (tonic), TCP | 44.8 (40.1–46.0) | 46.5 (45.7–47.0) | 54.0 (53.2–55.0) | 231.8 (230.2–232.1) |
| Zenoh, TCP | 58.2 (56.9–61.5) | 59.1 (58.4–59.1) | 62.4 (61.5–64.1) | 370.9 (368.3–375.0) |
| Raw pipe, no protocol | 4.6 (4.6–4.7) | 7.5 (7.5–7.5) | 8.4 (8.3–8.5) | 141.3 (135.5–147.1) |

## Python client and server

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 65.6 (37.8–66.5) | 75.0 (74.2–83.1) | 101.2 (98.8–105.0) | 901.8 (883.2–949.2) |
| NCP 2, pipe, no digest check | 66.2 (64.4–72.2) | 80.3 (79.0–81.2) | 78.8 (78.4–94.1) | 576.9 (566.5–583.0) |
| NCP 2, Unix socket | 66.5 (61.5–67.2) | 75.5 (67.6–83.4) | 99.8 (94.1–104.0) | 813.8 (803.2–825.9) |
| NCP 2, TCP | 72.0 (70.0–74.5) | 89.6 (82.0–90.5) | 105.0 (99.1–109.4) | 924.4 (922.4–950.4) |
| NCP 1.0.1, pipe | 476.5 (469.5–488.1) | 1286.2 (1281.0–1321.3) | 11557.6 (11480.9–11855.8) | not measured |
| gRPC (grpcio), Unix socket | 114.9 (114.7–115.9) | 117.5 (114.7–119.0) | 180.2 (174.4–193.5) | 3830.8 (3694.0–4377.2) |
| gRPC (grpcio), TCP | 129.1 (128.9–134.8) | 132.2 (126.0–133.0) | 136.8 (129.3–138.5) | 261.4 (256.8–266.4) |
| ZeroMQ, ipc | 53.2 (50.4–53.2) | 55.7 (55.1–56.1) | 73.3 (71.8–75.0) | 1011.7 (970.3–1025.8) |
| ZeroMQ, TCP | 58.8 (58.0–60.4) | 62.4 (61.5–64.0) | 79.5 (76.5–84.4) | 176.1 (175.6–184.0) |
| HTTP/1.1, TCP | 86.0 (85.8–87.3) | 81.3 (75.2–84.7) | 77.0 (63.0–79.0) | 145.1 (140.6–147.9) |
| Zenoh, TCP | 63.7 (62.2–64.2) | 64.9 (63.3–65.5) | 66.7 (66.5–67.3) | 149.0 (145.0–153.3) |
| Raw pipe, no protocol | 9.4 (9.0–10.0) | 10.0 (9.0–10.3) | 9.7 (9.6–11.9) | 188.1 (186.2–192.4) |

## Rust: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (tonic), Unix socket | 32.5 (31.9–36.0) | 31.5 (30.7–32.8) | 54.6 (53.7–55.3) | 1245.4 (1224.5–1255.5) |
| gRPC (tonic), Unix socket + SHA-256 | 35.1 (32.1–36.5) | 35.0 (34.7–38.3) | 74.6 (70.5–77.0) | 2013.6 (1937.5–2036.0) |
| gRPC (tonic), TCP + SHA-256 | 45.2 (42.8–46.6) | 48.6 (47.8–48.7) | 74.9 (73.6–75.9) | 1198.2 (1180.2–1210.8) |
| Zenoh, TCP + SHA-256 | 59.4 (58.8–59.5) | 62.1 (61.0–62.5) | 82.1 (82.0–84.0) | 1154.2 (1130.5–1156.0) |
| Raw pipe + SHA-256 | 5.1 (4.9–5.1) | 9.0 (7.9–9.2) | 26.9 (23.9–26.9) | 948.2 (873.2–962.9) |

## Python: arms of protocol 2

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 (1 MiB) |
| --- | ---: | ---: | ---: | ---: |
| gRPC (grpcio), Unix socket + SHA-256 | 122.5 (120.5–125.8) | 122.3 (122.2–122.6) | 190.0 (186.5–198.1) | 4476.3 (4205.4–4534.7) |
| gRPC (grpcio), TCP + SHA-256 | 133.3 (132.9–136.0) | 136.8 (134.2–137.8) | 156.5 (153.5–157.0) | 1032.1 (1001.8–1037.8) |
| ZeroMQ, ipc + SHA-256 | 58.5 (53.2–59.9) | 60.0 (58.2–61.3) | 96.4 (94.0–97.3) | 1645.8 (1629.6–1660.6) |
| ZeroMQ, TCP + SHA-256 | 64.4 (63.4–65.9) | 66.4 (66.2–68.5) | 102.2 (100.1–106.9) | 974.6 (967.2–993.0) |
| HTTP/1.1, TCP + SHA-256 | 84.1 (81.4–87.3) | 88.5 (88.3–89.1) | 93.0 (91.2–96.4) | 908.8 (899.5–929.2) |
| Zenoh, TCP + SHA-256 | 67.8 (67.5–68.2) | 68.8 (67.6–69.5) | 86.7 (86.5–88.5) | 862.8 (832.9–873.2) |
| Raw pipe + SHA-256 | 7.8 (7.8–11.0) | 14.5 (10.9–14.5) | 33.1 (25.1–34.0) | 864.5 (851.1–890.2) |

## Mixed languages over pipes

| Client, owner | N | NCP 2 | NCP 1.0.1 | Ratio |
| --- | ---: | ---: | ---: | ---: |
| Rust, Rust | 0 | 11.0 | 41.0 | 3.74 |
| Rust, Rust | 127 | 17.2 | 73.3 | 4.26 |
| Rust, Rust | 1788 | 36.1 | 433.7 | 12 |
| Rust, Python | 0 | 29.2 | 214.8 | 7.35 |
| Rust, Python | 127 | 36.1 | 683.2 | 18.9 |
| Rust, Python | 1788 | 51.7 | 6569.5 | 127 |
| Python, Rust | 0 | 28.9 | 250.0 | 8.66 |
| Python, Rust | 127 | 38.3 | 635.5 | 16.6 |
| Python, Rust | 1788 | 52.9 | 5380.9 | 102 |
| Python, Python | 0 | 65.6 | 476.5 | 7.26 |
| Python, Python | 127 | 75.0 | 1286.2 | 17.1 |
| Python, Python | 1788 | 101.2 | 11557.6 | 114 |

## Hypotheses

| # | Supported | Detail |
| --- | --- | --- |
| H1 | yes | 12 of 12 comparisons hold |
| H2 | yes | ncp2-rust-rust-pipe-n0: 11.0 µs (limit 15); ncp2-python-python-pipe-n0: 65.6 µs (limit 150); ncp2-python-python-pipe-n127: 75.0 µs (limit 150) |
| H3 | yes | 6.3 µs added (limit 10) |
| H4 | yes | 10 of 10 comparisons hold |
| H5 | no | 7 of 9 comparisons hold; ncp2-python-python-pipe-n127 not below http-python-tcp-n127; ncp2-python-python-pipe-n1788 not below http-python-tcp-n1788 |
| R1 | no | 4 of H1 to H5 hold again: H1, H2, H3, H4 |
| R2 | yes | 9 of 9 comparisons hold |
| R3 | yes | 6 of 6 comparisons hold |

## Where the time of an NCP 2 call goes, over pipes

| Language | N | Floor | Rest of NCP 2 | Digest comparison | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.6 | 6.0 | 0.4† | 11.0 |
| Rust | 127 | 7.5 | 8.7 | 1.0 | 17.2 |
| Rust | 1788 | 8.4 | 16.9 | 10.8 | 36.1 |
| Rust | 87381 | 141.3 | 419.3 | 378.9 | 939.5 |
| Python | 0 | 9.4 | 56.8 | 0.0† (below zero: digest, drawn as zero) | 65.6 |
| Python | 127 | 10.0 | 70.4 | 0.0† (below zero: digest, drawn as zero) | 75.0 |
| Python | 1788 | 9.7 | 69.1 | 22.5 | 101.2 |
| Python | 87381 | 188.1 | 388.8 | 324.9 | 901.8 |

† Smaller than the spread of the block medians of the two arms that give the part: variation between runs, not a measured cost.

## The integrity check alone, over pipes (exploratory)

Check: the raw pipe with SHA-256 at both ends minus the raw pipe. Rest of NCP 2: NCP 2 minus the raw pipe with SHA-256; below zero when NCP 2 is faster than the raw pipe with the same check.

| Language | N | Raw pipe | Check | Rest of NCP 2 | NCP 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rust | 0 | 4.6 | 0.5 | 5.9 | 11.0 |
| Rust | 127 | 7.5 | 1.5 | 8.2 | 17.2 |
| Rust | 1788 | 8.4 | 18.5 | 9.2 | 36.1 |
| Rust | 87381 | 141.3 | 807.0 | -8.8 | 939.5 |
| Python | 0 | 9.4 | -1.6 | 57.8 | 65.6 |
| Python | 127 | 10.0 | 4.5 | 60.6 | 75.0 |
| Python | 1788 | 9.7 | 23.5 | 68.1 | 101.2 |
| Python | 87381 | 188.1 | 676.4 | 37.3 | 901.8 |
