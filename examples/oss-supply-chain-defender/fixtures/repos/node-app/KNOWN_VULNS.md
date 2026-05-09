# Known vulnerabilities in this fixture

This file documents the deliberate vulnerabilities for AURORA's demo. Real
NVD/OSV lookups should surface all of these. If they don't, AURORA's
`vuln-lookup` agent has a bug.

| Package          | Version pinned | CVE / Advisory                                  | CVSS | Severity expected |
|------------------|----------------|-------------------------------------------------|------|-------------------|
| `lodash`         | 4.17.20        | CVE-2021-23337 (Command Injection via template) | 7.2  | high              |
| `minimist`       | 0.2.0          | CVE-2021-44906 (Prototype Pollution)            | 9.8  | critical          |
| `axios`          | 0.21.0         | CVE-2021-3749 (ReDoS in trim regex)             | 7.5  | high              |
| `jsonwebtoken`   | 8.5.1          | CVE-2022-23529 (algorithm confusion)            | 9.8  | critical          |
| `express`        | 4.17.1         | CVE-2022-24999 (qs DoS via deeply-nested keys)  | 7.5  | high              |

The DMN severity matrix should classify the worst as **critical** because
`minimist` and `jsonwebtoken` both score ≥ 9.0 and have known exploits.
