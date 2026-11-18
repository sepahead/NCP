# Comparison benchmark: results of protocol 4

Runs: 84; commit `c5036d5`; from 2026-11-18T20:36:46.215860Z.

| Arm | N = 0 | N = 127 | N = 1788 | N = 87381 |
| --- | ---: | ---: | ---: | ---: |
| `iox2-rust-shm` | 0.791 (0.708 to 0.792) | 0.833 (0.75 to 0.834) | 1.25 (1.17 to 1.25) | 26.3 (25.7 to 26.7) |
| `ncp2-rust-rust-pipe` | 10.9 (10 to 10.9) | 17 (15.3 to 17.5) | 34.2 (33.7 to 36.7) | 920 (910 to 1e+03) |
| `ncp2-rust-rust-unix` | 11.1 (11.1 to 12.2) | 16.8 (16.8 to 16.9) | 35 (34.8 to 36.8) | 808 (807 to 872) |
| `ncp2-rust-rust-tcp` | 26.8 (25.6 to 27.3) | 32.2 (32 to 32.8) | 51.3 (51.2 to 53.9) | 966 (961 to 1.05e+03) |
| `raw-rust-pipe` | 4.67 (4.54 to 4.75) | 7.5 (4.92 to 7.54) | 8.38 (8.33 to 8.42) | 152 (147 to 170) |
| `iox2-rust-shm-sha256` | 0.959 (0.958 to 1) | 2.21 (1.96 to 2.92) | 16 (16 to 17.9) | 748 (748 to 834) |
| `raw-rust-pipe-sha256` | 5.08 (4.96 to 5.08) | 9.04 (8.92 to 9.08) | 23.8 (23.4 to 27.1) | 880 (879 to 927) |

Statistic in µs: the median of the three block medians, with their range.

- Q1: supported
- Q2: supported
