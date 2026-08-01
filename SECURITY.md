# Security policy

## Reporting

Please report vulnerabilities privately through GitHub Security Advisories rather than a public
issue.

## Trust boundary

Keryx treats every remote feed and every field inside it as untrusted data. Feed values are
serialized as data and are never shell commands, templates, permissions, or model instructions.

The first release accepts only absolute HTTPS feed URLs, limits each response to 20 MiB, uses a
bounded network timeout, and verifies that the final redirect remains HTTPS. Operators should only
configure sources they trust to publish public job data.

Keryx stores no applicant profile, résumé, authentication token, Discord credential, or job
application. Downstream consumers must keep those values outside public feeds and logs.

## Known boundary

The local CLI accepts operator-controlled feed URLs. It is not currently designed as a remotely
callable arbitrary-URL fetch service. A server that exposes source configuration to untrusted users
must add DNS/IP validation and per-tenant isolation before deployment.

