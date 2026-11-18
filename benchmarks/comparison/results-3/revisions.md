# NCP 2 arms: results-3 against results-2

Exploratory (PROTOCOL-3.md, section 6). Statistic: the median of the three block medians, in µs; range: the smallest to the largest block median. A ratio below 1 means that the later SDKs are faster.

| Configuration | results-2 | results-3 | Ratio | Ranges overlap |
| --- | ---: | ---: | ---: | --- |
| `ncp2-python-python-pipe-n0` | 38.8 | 65.6 | 1.69 | yes |
| `ncp2-python-python-pipe-n127` | 49.2 | 75 | 1.53 | no |
| `ncp2-python-python-pipe-n1788` | 67.2 | 101 | 1.51 | no |
| `ncp2-python-python-pipe-n87381` | 909 | 902 | 0.99 | yes |
| `ncp2-python-python-pipe-nocheck-n0` | 37.2 | 66.2 | 1.78 | no |
| `ncp2-python-python-pipe-nocheck-n127` | 47.9 | 80.3 | 1.68 | no |
| `ncp2-python-python-pipe-nocheck-n1788` | 57.4 | 78.8 | 1.37 | no |
| `ncp2-python-python-pipe-nocheck-n87381` | 565 | 577 | 1.02 | yes |
| `ncp2-python-python-tcp-n0` | 48.4 | 72 | 1.49 | no |
| `ncp2-python-python-tcp-n127` | 59.8 | 89.6 | 1.50 | no |
| `ncp2-python-python-tcp-n1788` | 85.4 | 105 | 1.23 | no |
| `ncp2-python-python-tcp-n87381` | 920 | 924 | 1.00 | yes |
| `ncp2-python-python-unix-n0` | 38.9 | 66.5 | 1.71 | no |
| `ncp2-python-python-unix-n127` | 57.2 | 75.5 | 1.32 | no |
| `ncp2-python-python-unix-n1788` | 70.2 | 99.8 | 1.42 | no |
| `ncp2-python-python-unix-n87381` | 759 | 814 | 1.07 | no |
| `ncp2-python-rust-pipe-n0` | 19.2 | 28.9 | 1.51 | no |
| `ncp2-python-rust-pipe-n127` | 28.3 | 38.3 | 1.35 | no |
| `ncp2-python-rust-pipe-n1788` | 44 | 52.9 | 1.20 | yes |
| `ncp2-python-rust-pipe-n87381` | 894 | 926 | 1.04 | yes |
| `ncp2-rust-python-pipe-n0` | 19.6 | 29.2 | 1.49 | no |
| `ncp2-rust-python-pipe-n127` | 28.2 | 36.1 | 1.28 | no |
| `ncp2-rust-python-pipe-n1788` | 48 | 51.7 | 1.08 | yes |
| `ncp2-rust-python-pipe-n87381` | 885 | 909 | 1.03 | no |
| `ncp2-rust-rust-pipe-n0` | 9 | 11 | 1.22 | no |
| `ncp2-rust-rust-pipe-n127` | 13.9 | 17.2 | 1.24 | no |
| `ncp2-rust-rust-pipe-n1788` | 32.5 | 36.1 | 1.11 | no |
| `ncp2-rust-rust-pipe-n87381` | 918 | 940 | 1.02 | yes |
| `ncp2-rust-rust-pipe-nocheck-n0` | 9.04 | 10.6 | 1.17 | no |
| `ncp2-rust-rust-pipe-nocheck-n127` | 12.9 | 16.2 | 1.25 | no |
| `ncp2-rust-rust-pipe-nocheck-n1788` | 23.7 | 25.2 | 1.07 | no |
| `ncp2-rust-rust-pipe-nocheck-n87381` | 530 | 561 | 1.06 | yes |
| `ncp2-rust-rust-tcp-n0` | 27 | 25.6 | 0.95 | yes |
| `ncp2-rust-rust-tcp-n127` | 30.8 | 31.9 | 1.04 | yes |
| `ncp2-rust-rust-tcp-n1788` | 51.1 | 51.5 | 1.01 | yes |
| `ncp2-rust-rust-tcp-n87381` | 1.01e+03 | 1.04e+03 | 1.03 | yes |
| `ncp2-rust-rust-unix-n0` | 9.46 | 12.2 | 1.29 | no |
| `ncp2-rust-rust-unix-n127` | 14.1 | 18.4 | 1.30 | no |
| `ncp2-rust-rust-unix-n1788` | 33 | 37.2 | 1.13 | no |
| `ncp2-rust-rust-unix-n87381` | 872 | 895 | 1.03 | no |
