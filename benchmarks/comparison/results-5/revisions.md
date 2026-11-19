# NCP 2 arms: results-5 against results-3

Exploratory (PROTOCOL-3.md, section 6). Statistic: the median of the three block medians, in µs; range: the smallest to the largest block median. A ratio below 1 means that the later SDKs are faster.

| Configuration | results-3 | results-5 | Ratio | Ranges overlap |
| --- | ---: | ---: | ---: | --- |
| `ncp2-python-python-pipe-n0` | 65.6 | 52.4 | 0.80 | yes |
| `ncp2-python-python-pipe-n127` | 75 | 73.2 | 0.98 | no |
| `ncp2-python-python-pipe-n1788` | 101 | 84.1 | 0.83 | no |
| `ncp2-python-python-pipe-n87381` | 902 | 834 | 0.93 | no |
| `ncp2-python-python-pipe-nocheck-n0` | 66.2 | 57.2 | 0.86 | no |
| `ncp2-python-python-pipe-nocheck-n127` | 80.3 | 68.8 | 0.86 | no |
| `ncp2-python-python-pipe-nocheck-n1788` | 78.8 | 78.2 | 0.99 | yes |
| `ncp2-python-python-pipe-nocheck-n87381` | 577 | 536 | 0.93 | no |
| `ncp2-python-python-tcp-n0` | 72 | 62 | 0.86 | no |
| `ncp2-python-python-tcp-n127` | 89.6 | 75.4 | 0.84 | yes |
| `ncp2-python-python-tcp-n1788` | 105 | 90.5 | 0.86 | no |
| `ncp2-python-python-tcp-n87381` | 924 | 882 | 0.95 | yes |
| `ncp2-python-python-unix-n0` | 66.5 | 56.7 | 0.85 | no |
| `ncp2-python-python-unix-n127` | 75.5 | 66.5 | 0.88 | yes |
| `ncp2-python-python-unix-n1788` | 99.8 | 84.7 | 0.85 | no |
| `ncp2-python-python-unix-n87381` | 814 | 740 | 0.91 | yes |
| `ncp2-python-rust-pipe-n0` | 28.9 | 25.3 | 0.88 | no |
| `ncp2-python-rust-pipe-n127` | 38.3 | 31.6 | 0.82 | no |
| `ncp2-python-rust-pipe-n1788` | 52.9 | 54.9 | 1.04 | yes |
| `ncp2-python-rust-pipe-n87381` | 926 | 870 | 0.94 | no |
| `ncp2-rust-python-pipe-n0` | 29.2 | 26.7 | 0.91 | no |
| `ncp2-rust-python-pipe-n127` | 36.1 | 30.6 | 0.85 | no |
| `ncp2-rust-python-pipe-n1788` | 51.7 | 49.5 | 0.96 | yes |
| `ncp2-rust-python-pipe-n87381` | 909 | 852 | 0.94 | yes |
| `ncp2-rust-rust-pipe-n0` | 11 | 9.88 | 0.90 | no |
| `ncp2-rust-rust-pipe-n127` | 17.2 | 15.2 | 0.89 | no |
| `ncp2-rust-rust-pipe-n1788` | 36.1 | 33 | 0.91 | no |
| `ncp2-rust-rust-pipe-n87381` | 940 | 901 | 0.96 | no |
| `ncp2-rust-rust-pipe-nocheck-n0` | 10.6 | 9.67 | 0.91 | no |
| `ncp2-rust-rust-pipe-nocheck-n127` | 16.2 | 14.2 | 0.88 | no |
| `ncp2-rust-rust-pipe-nocheck-n1788` | 25.2 | 24.5 | 0.97 | yes |
| `ncp2-rust-rust-pipe-nocheck-n87381` | 561 | 539 | 0.96 | no |
| `ncp2-rust-rust-tcp-n0` | 25.6 | 26.8 | 1.04 | yes |
| `ncp2-rust-rust-tcp-n127` | 31.9 | 31.2 | 0.98 | no |
| `ncp2-rust-rust-tcp-n1788` | 51.5 | 52 | 1.01 | yes |
| `ncp2-rust-rust-tcp-n87381` | 1.04e+03 | 964 | 0.93 | no |
| `ncp2-rust-rust-unix-n0` | 12.2 | 11 | 0.90 | yes |
| `ncp2-rust-rust-unix-n127` | 18.4 | 16.4 | 0.89 | no |
| `ncp2-rust-rust-unix-n1788` | 37.2 | 34.2 | 0.92 | no |
| `ncp2-rust-rust-unix-n87381` | 895 | 802 | 0.90 | no |
