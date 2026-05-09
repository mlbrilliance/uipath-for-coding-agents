# Known vulnerabilities in this fixture

| Package        | Version pinned | CVE / Advisory                            | CVSS | Severity expected |
|----------------|----------------|-------------------------------------------|------|-------------------|
| `pyyaml`       | 5.3.1          | CVE-2020-14343 (RCE via FullLoader)       | 9.8  | critical          |
| `requests`     | 2.25.0         | CVE-2023-32681 (Proxy auth leak)          | 6.1  | medium            |
| `urllib3`      | 1.26.4         | CVE-2021-33503 (ReDoS in URL parser)      | 7.5  | high              |
| `jinja2`       | 2.11.2         | CVE-2020-28493 (sandbox bypass)           | 5.3  | medium            |
| `cryptography` | 3.2            | CVE-2020-25659 (Bleichenbacher timing)    | 5.9  | medium            |
| `pillow`       | 8.0.0          | CVE-2021-25287 (out-of-bounds read)       | 7.5  | high              |
