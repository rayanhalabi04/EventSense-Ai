#!/usr/bin/env bash
#
# Smoke test for the EventSense AI dockerized stack (Spec 017).
#
# Checks: /health readiness -> demo login -> classify a simulated message.
# (The RAG no-source check is skipped until Spec 009 is implemented.)
#
# Prints [PASS]/[FAIL]/[SKIP] per check, writes a machine-readable result to
# eval-artifacts/docker_smoke.json (consumed by Spec 015 `docker_smoke`), and
# exits non-zero if any non-skipped check fails. Never prints secrets/tokens.
#
set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

env_value() { # key
  if [ -f "${REPO_ROOT}/.env" ]; then
    python3 - "$1" "${REPO_ROOT}/.env" <<'PY'
import sys

key, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    for raw in fh:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            print(value.strip().strip('"').strip("'"))
            break
PY
  fi
}

if [ -z "${API_BASE_URL:-}" ]; then
  API_HOST_PORT_FROM_ENV="$(env_value API_HOST_PORT)"
  API_BASE_URL_FROM_ENV="$(env_value API_BASE_URL)"
  if [ -n "${API_BASE_URL_FROM_ENV}" ]; then
    API_BASE_URL="${API_BASE_URL_FROM_ENV}"
  else
    API_BASE_URL="http://localhost:${API_HOST_PORT_FROM_ENV:-8000}"
  fi
fi
SMOKE_USER_EMAIL="${SMOKE_USER_EMAIL:-admin@elegant-weddings.demo}"
SMOKE_USER_PASSWORD="${SMOKE_USER_PASSWORD:-demo-password-1}"
SMOKE_TENANT_SLUG="${SMOKE_TENANT_SLUG:-elegant-weddings}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"

ARTIFACT_DIR="${REPO_ROOT}/eval-artifacts"
ARTIFACT="${ARTIFACT_DIR}/docker_smoke.json"
mkdir -p "${ARTIFACT_DIR}"

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Parallel arrays of check results: name|passed(true/false/skip)|detail
CHECK_NAMES=()
CHECK_PASSED=()
CHECK_DETAIL=()
OVERALL_OK=1

record() { # name passed detail
  CHECK_NAMES+=("$1"); CHECK_PASSED+=("$2"); CHECK_DETAIL+=("$3")
  case "$2" in
    true)  echo "[PASS] $1 — $3" ;;
    skip)  echo "[SKIP] $1 — $3" ;;
    *)     echo "[FAIL] $1 — $3"; OVERALL_OK=0 ;;
  esac
}

# Read a top-level string field from a JSON blob without requiring jq.
json_get() { # json key
  printf '%s' "$1" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    v=d.get('$2')
    print('' if v is None else v)
except Exception:
    print('')"
}

# --- Check 1: /health readiness (with retry while the stack warms up) -------
health_body=""
health_ok=0
for _ in $(seq 1 "${HEALTH_RETRIES}"); do
  code="$(curl -s -o /tmp/smoke_health.$$ -w '%{http_code}' "${API_BASE_URL}/health" 2>/dev/null || echo 000)"
  health_body="$(cat /tmp/smoke_health.$$ 2>/dev/null || true)"
  if [ "${code}" = "200" ]; then health_ok=1; break; fi
  sleep "${HEALTH_INTERVAL}"
done
rm -f /tmp/smoke_health.$$
if [ "${health_ok}" = "1" ]; then
  status="$(json_get "${health_body}" status)"
  classifier="$(json_get "${health_body}" classifier)"
  record "health" true "status=${status} classifier=${classifier}"
else
  record "health" false "no 200 from ${API_BASE_URL}/health after ${HEALTH_RETRIES} tries (last code=${code})"
fi

# --- Check 2: demo login -----------------------------------------------------
token=""
if [ "${health_ok}" = "1" ]; then
  login_payload="$(E="${SMOKE_USER_EMAIL}" P="${SMOKE_USER_PASSWORD}" T="${SMOKE_TENANT_SLUG}" \
    python3 -c "import json,os
print(json.dumps({'email':os.environ['E'],'password':os.environ['P'],'tenant_slug':os.environ['T']}))")"
  login_body="$(curl -s -X POST "${API_BASE_URL}/auth/token" \
    -H 'Content-Type: application/json' -d "${login_payload}" 2>/dev/null || true)"
  token="$(json_get "${login_body}" access_token)"
  if [ -n "${token}" ]; then
    record "login" true "authenticated demo user (token not shown)"
  else
    record "login" false "login failed for ${SMOKE_TENANT_SLUG} (no access_token returned)"
  fi
else
  record "login" false "skipped: health not ready"
fi

# --- Check 3: classify a simulated message ----------------------------------
if [ -n "${token}" ]; then
  msg_payload='{"client_name":"Smoke Test Client","body":"How much does your gold wedding package cost?"}'
  msg_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/simulator/messages" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${msg_payload}" 2>/dev/null || true)"
  intent="$(json_get "${msg_body}" intent_label)"
  msg_id="$(json_get "${msg_body}" message_id)"
  if [ -n "${msg_id}" ] && [ -n "${intent}" ]; then
    record "classify" true "message classified as intent=${intent}"
  else
    record "classify" false "message not created/classified"
  fi
else
  record "classify" false "skipped: no auth token"
fi

# --- Check 4: tenant-scoped RAG no-source refusal (deferred to Spec 009) -----
record "rag_no_source" skip "RAG (Spec 009) not yet implemented"

# --- Write the JSON artifact -------------------------------------------------
COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PASSED_BOOL=$([ "${OVERALL_OK}" = "1" ] && echo true || echo false)

NAMES="${CHECK_NAMES[*]}" PASSEDV="${CHECK_PASSED[*]}" DETAILS=$(printf '%s\n' "${CHECK_DETAIL[@]}") \
PASSED="${PASSED_BOOL}" STARTED="${STARTED_AT}" COMPLETED="${COMPLETED_AT}" \
python3 - "${ARTIFACT}" <<'PY'
import json, os, sys
names = os.environ["NAMES"].split(" ")
passed = os.environ["PASSEDV"].split(" ")
details = os.environ["DETAILS"].split("\n")
checks = []
for i, name in enumerate(names):
    raw = passed[i] if i < len(passed) else "false"
    checks.append({
        "name": name,
        "passed": True if raw == "true" else (None if raw == "skip" else False),
        "skipped": raw == "skip",
        "detail": details[i] if i < len(details) else "",
    })
out = {
    "passed": os.environ["PASSED"] == "true",
    "started_at": os.environ["STARTED"],
    "completed_at": os.environ["COMPLETED"],
    "checks": checks,
}
with open(sys.argv[1], "w") as fh:
    json.dump(out, fh, indent=2)
PY

echo ""
echo "Result written to ${ARTIFACT}"
if [ "${OVERALL_OK}" = "1" ]; then
  echo "=> SMOKE PASSED"
  exit 0
else
  echo "=> SMOKE FAILED"
  exit 1
fi
