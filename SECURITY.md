# Security Policy

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting
("Security" tab -> "Report a vulnerability") for this repository.

## Principles

- No secrets in Git, Dockerfiles, Terraform source, workflow YAML or application code.
- CI/CD authenticates to AWS using GitHub OIDC; no long-lived AWS access keys.
- Least-privilege IAM, private database networking, encryption in transit and at rest.
- Internal error details are never returned to API consumers.

Detailed security architecture will be documented in `docs/security/` as the platform is built.

## Automated scanning

Dependency, secret, container-image and misconfiguration scans run through
`scripts/security.sh`, on every pull request and on a schedule. What each tool is for, how
findings are triaged and how suppressions work: `docs/security/scanning.md`.
