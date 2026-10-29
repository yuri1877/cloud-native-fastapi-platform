# Security scanning

`scripts/security.sh` runs the scans below. They need the network (vulnerability databases) and
external tools, so they are separate from `scripts/check.sh`. CI runs them on every pull request
**and on a schedule**: new advisories are published daily against code that has not changed, so a
build that passed last week can fail today without a commit.

| Category | Tool | What it catches | What it does not | Run |
|---|---|---|---|---|
| Dependency vulnerabilities | pip-audit | Known advisories for the runtime dependencies exactly as locked (`uv export --frozen --no-dev`, with hashes). `--strict`: a dependency it cannot audit fails the scan. | Vulnerabilities in dev tools; unreported flaws; whether your code reaches the vulnerable function. | `scripts/security.sh deps` |
| Secrets | gitleaks | Credentials in the working tree **and in git history**, using its default ruleset (cloud keys, tokens, private keys, high-entropy strings). | Secrets in a format no rule knows; anything stored outside the repository. | `scripts/security.sh secrets` |
| Image vulnerabilities | Trivy | OS packages and Python libraries in the built image. Fixable HIGH and CRITICAL findings fail; unfixed ones are reported, not failed (`--ignore-unfixed`). | Flaws with no advisory yet; how the container behaves at runtime. | `scripts/security.sh image` |
| Misconfiguration | Trivy | HIGH and CRITICAL misconfigurations: the Dockerfile today, Terraform once it exists (Phase 21). | Whether a configuration is *correct* for its purpose. | `scripts/security.sh config` |
| SAST | ruff `S` rules; CodeQL (CI, Phase 29) | Ruff: bandit-derived patterns such as hard-coded credentials, `assert` in application code, shell and SQL injection patterns, weak crypto. CodeQL: data-flow (taint) analysis across functions. | Business-logic and authorisation mistakes, which are what the contract and RBAC tests are for. | `scripts/check.sh`; CI |

## Why these tools, and not others
- **No separate bandit.** Ruff's `S` rules are bandit's rules; running both would report the same
  findings twice.
- **No tfsec or Checkov.** Trivy's misconfiguration scanner includes tfsec's rules, so one tool
  covers the image and the infrastructure code.
- **CodeQL is CI-only** and is wired in Phase 29. It is free for public repositories; for a
  private one without GitHub Advanced Security, Semgrep's open-source CLI is the alternative.
  That decision is made when the workflow is written.
- **No commercial scanners:** they add accounts and cost without covering anything these do not.

Each addition has to say what it catches that the existing tools do not.

## Failing and suppressing
A scan that finds something fails the run, and a scan whose tool is missing is an **error, not a
skip**: a scan that did not run is not a pass. Suppressions are narrow, written down and expire:

- **Vulnerabilities (pip-audit):** `scripts/pip-audit-ignores.txt`, one ID per line with a reason
  and `(until YYYY-MM-DD)`. A guard test fails when the date passes, so the exception has to be
  renewed with a fresh justification or removed.
- **Vulnerabilities (Trivy):** `.trivyignore.yaml` with a `statement` and `expired_at` per entry.
  Not created until needed.
- **Secrets:** `.gitleaks.toml` may exempt (a) generated content that is not source (the lock file,
  caches, the virtualenv), by path, and (b) a known fake value, as the **exact string**. It must
  never exempt a source directory or use a wildcard pattern; guard tests enforce both.

## When a scan finds something
1. **Secret:** assume it is compromised. Rotate it first, then remove it from history. Only then
   decide whether it was a fake.
2. **Dependency with a fix:** `uv lock --upgrade-package <name>`, `uv sync`, `scripts/check.sh`.
3. **Dependency with no fix:** mitigate, or accept it in the ignore file with a reason and expiry.
4. **Image:** rebuild with `docker build --pull` for a fresh base image; most findings are OS
   packages that clear on a rebuild. Otherwise update the dependency.
5. **Misconfiguration:** fix it, or explain in the pull request why it is acceptable.

Base images are pinned through build arguments (`docs/deployment/docker.md`), which Dependabot
cannot read, so bumping them is manual until the pipeline pins them by digest (Phase 29).

## Known limits of the scanners
- They find *known* problems; a clean run is not a proof of security.
- Vulnerability databases lag publication, which is why the scheduled run matters.
- `--ignore-unfixed` keeps the image scan usable, but it hides unfixed vulnerabilities from the
  gate; they still appear in the report and should be reviewed.
- Scanners produce false positives. Triage each one; do not blanket-exempt.

## Not done yet
- **CI wiring:** a pull-request job and a nightly job that call `scripts/security.sh`, plus CodeQL
  (Phase 29).
- **Terraform scanning:** the `config` scan covers it automatically once `terraform/` has content
  (Phase 21 onward).
- **SBOM generation and image signing.**
- **A gitleaks pre-commit hook** (optional; needs the binary on every developer machine).
- **Repository settings** worth enabling on GitHub: secret scanning with push protection, and
  Dependabot alerts.

## Testing
`tests/unit/test_security_config.py` checks that the script is executable and stops at the first
failure; that Trivy runs with `--exit-code 1` and nothing swallows a failure; that a missing tool
is an error; that pip-audit audits the locked runtime set with `--strict`; that gitleaks scans the
tree and the history, extends its default rules and never exempts a source directory or uses a
wildcard; that accepted vulnerabilities carry a reason and an unexpired date; and that Dependabot
watches the Python dependencies.
