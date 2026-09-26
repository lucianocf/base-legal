# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through GitHub's
[private vulnerability reporting](../../security/advisories/new) for this
repository. Include steps to reproduce, the affected version/commit and the
impact you observed.

You can expect an acknowledgement within 5 business days and a status update
within 15 business days. Fixes are released as patch versions and credited in
the advisory unless you prefer to stay anonymous.

## Scope

In scope: the `base_legal` package, its CLI/API/MCP adapters, the ingestion
pipeline, the corpus integrity checks and the CI/CD configuration of this
repository. Of particular interest:

- prompt injection that bypasses citation validation or strict refusal;
- personal data reaching a third party unredacted, or being logged;
- user questions reaching Voyage AI (they must be embedded locally);
- tampering with the corpus, model weights or precomputed vectors that the
  integrity checks fail to detect;
- supply chain issues in dependencies or workflows.

Out of scope: the correctness of legal interpretation (open a regular issue),
vulnerabilities in third-party services themselves, and self-hosted deployments
that disable the documented controls.

## Supported versions

Only the latest release receives security fixes during the 0.x series.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) and
[docs/PRIVACY.md](docs/PRIVACY.md) for the design this policy protects.
