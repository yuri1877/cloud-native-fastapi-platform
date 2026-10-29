#!/usr/bin/env bash
# Security scans. They need the network (vulnerability databases) and external tools, so they are
# not part of scripts/check.sh. CI runs them on every pull request and on a schedule, because new
# advisories are published daily against code that has not changed.
#
#   scripts/security.sh [deps|secrets|config|image|all]      default: all
#
# A tool that is missing is an error, never a silent skip: a scan that did not run is not a pass.
#   brew install gitleaks trivy     (pip-audit comes with `uv sync`; the image scan needs Docker)
# Set SKIP_BUILD=1 to scan an image you already built; IMAGE names it.
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-cloud-native-fastapi-platform:security-scan}"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

step() { printf '\n==> %s\n' "$1"; }

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: $1 is not installed. $2" >&2
    exit 3
  fi
}

scan_deps() {
  need uv "See https://docs.astral.sh/uv/"
  step "dependency vulnerabilities (pip-audit, runtime dependencies exactly as locked)"
  uv export --frozen --no-dev --no-emit-project --quiet --output-file "$workdir/requirements.txt"
  local -a ignores
  ignores=()
  local id
  for id in $(awk '!/^[[:space:]]*(#|$)/ { print $1 }' scripts/pip-audit-ignores.txt); do
    ignores+=(--ignore-vuln "$id")
  done
  uv run --frozen pip-audit --requirement "$workdir/requirements.txt" \
    --no-deps --disable-pip --strict ${ignores[@]+"${ignores[@]}"}
}

scan_secrets() {
  need gitleaks "Install: brew install gitleaks (8.19 or newer)"
  step "secrets in the working tree"
  gitleaks dir . --config .gitleaks.toml --redact --no-banner
  step "secrets in git history"
  gitleaks git . --config .gitleaks.toml --redact --no-banner
}

scan_config() {
  need trivy "Install: brew install trivy"
  step "misconfiguration (the Dockerfile today; Terraform once it exists)"
  trivy config --exit-code 1 --severity HIGH,CRITICAL --skip-dirs .venv .
}

scan_image() {
  need trivy "Install: brew install trivy"
  if [ "${SKIP_BUILD:-0}" != "1" ]; then
    need docker "Start Docker, or build the image yourself and set SKIP_BUILD=1"
    need uv "See https://docs.astral.sh/uv/"
    step "build the image to scan"
    docker build --build-arg "UV_VERSION=$(uv --version | awk '{print $2}')" --tag "$IMAGE" .
  fi
  step "image vulnerabilities (OS packages and Python libraries; fixable HIGH and CRITICAL fail)"
  trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE"
}

preflight_all() {
  need uv "See https://docs.astral.sh/uv/"
  need gitleaks "Install: brew install gitleaks (8.19 or newer)"
  need trivy "Install: brew install trivy"
  need docker "Start Docker, or run the other scans one at a time"
}

case "${1:-all}" in
  deps) scan_deps ;;
  secrets) scan_secrets ;;
  config) scan_config ;;
  image) scan_image ;;
  all) preflight_all; scan_deps; scan_secrets; scan_config; scan_image ;;
  *) echo "usage: scripts/security.sh [deps|secrets|config|image|all]" >&2; exit 2 ;;
esac

printf '\nSecurity scans passed.\n'
