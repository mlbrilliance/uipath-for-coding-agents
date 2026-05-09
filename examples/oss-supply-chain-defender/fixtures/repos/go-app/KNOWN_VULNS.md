# Known vulnerabilities in this fixture

| Package                            | Version pinned        | CVE / GHSA                                       | CVSS | Severity expected |
|------------------------------------|-----------------------|--------------------------------------------------|------|-------------------|
| `github.com/gin-gonic/gin`         | 1.7.0                 | CVE-2020-28483 (header injection)                | 7.5  | high              |
| `github.com/dgrijalva/jwt-go`      | 3.2.0+incompatible    | GHSA-w73w-5m7g-f7qc (deprecated; alg confusion)  | 7.5  | high              |
| `github.com/labstack/echo/v4`      | 4.6.0                 | CVE-2021-43798 (open redirect, fixed in 4.6.2)   | 6.1  | medium            |
| `golang.org/x/crypto`              | v0.0.0-2022...        | CVE-2023-48795 (Terrapin SSH protocol attack)    | 5.9  | medium            |
| `golang.org/x/text`                | 0.3.7                 | CVE-2022-32149 (DoS via Accept-Language)         | 7.5  | high              |
| `gopkg.in/yaml.v2`                 | 2.2.2                 | CVE-2019-11254 (DoS via large alias chain)       | 7.5  | high              |
