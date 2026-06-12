#!/usr/bin/env bash
#
# Smoke test for the EventSense AI dockerized stack (Spec 017).
#
# Checks: /health readiness -> demo login -> classify a simulated message ->
# create a tenant document -> generate a grounded suggested reply -> verify an
# unsupported refusal -> verify audit logs.
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
  JSON_INPUT="$1" python3 - "$2" <<'PY'
import json
import os
import sys

path = sys.argv[1].split(".")
try:
    value = json.loads(os.environ.get("JSON_INPUT", ""))
    for part in path:
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
        if value is None:
            break
    if value is None:
        print("")
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)
except Exception:
    print("")
PY
}

json_len() { # json path
  JSON_INPUT="$1" python3 - "$2" <<'PY'
import json
import os
import sys

path = sys.argv[1].split(".") if sys.argv[1] else []
try:
    value = json.loads(os.environ.get("JSON_INPUT", ""))
    for part in path:
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
        if value is None:
            break
    print(len(value) if isinstance(value, list) else 0)
except Exception:
    print(0)
PY
}

json_audit_has_reply_event() { # json event_type suggested_reply_id
  JSON_INPUT="$1" python3 - "$2" "$3" <<'PY'
import json
import os
import sys

event_type = sys.argv[1]
reply_id = sys.argv[2]
try:
    items = json.loads(os.environ.get("JSON_INPUT", ""))
    print(
        "true"
        if any(
            item.get("event_type") == event_type
            and item.get("details", {}).get("suggested_reply_id") == reply_id
            for item in items
        )
        else "false"
    )
except Exception:
    print("false")
PY
}

json_payload() {
  python3 - "$@" <<'PY'
import json
import sys

if len(sys.argv[1:]) % 2 != 0:
    raise SystemExit("json_payload requires key/value pairs")
print(json.dumps(dict(zip(sys.argv[1::2], sys.argv[2::2]))))
PY
}

json_safe_error_summary() {
  JSON_INPUT="$1" python3 <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ.get("JSON_INPUT", ""))
except Exception:
    print("non-JSON response")
    raise SystemExit

if isinstance(data, dict):
    keys = sorted(key for key in data.keys() if key != "access_token")
    parts = [f"keys={','.join(keys) if keys else 'none'}"]
    detail = data.get("detail")
    if isinstance(detail, str):
        parts.append(f"detail={detail}")
    elif isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict) and first.get("msg"):
            parts.append(f"detail={first.get('msg')}")
    error_code = data.get("error_code")
    if error_code:
        parts.append(f"error_code={error_code}")
    print(" ".join(parts))
else:
    print(f"json_type={type(data).__name__}")
PY
}

# --- Check 1: /health readiness (with retry while the stack warms up) -------
health_body=""
health_ok=0
for _ in $(seq 1 "${HEALTH_RETRIES}"); do
  code="$(curl -s -o /tmp/smoke_health.$$ -w '%{http_code}' "${API_BASE_URL}/health" 2>/dev/null)"
  if [ -z "${code}" ]; then code="000"; fi
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
  login_payload="$(json_payload email "${SMOKE_USER_EMAIL}" password "${SMOKE_USER_PASSWORD}")"
  login_body_file="/tmp/smoke_login.$$"
  login_code="$(curl -s -o "${login_body_file}" -w '%{http_code}' \
    -X POST "${API_BASE_URL}/api/v1/auth/login" \
    -H 'Content-Type: application/json' -d "${login_payload}" 2>/dev/null)"
  if [ -z "${login_code}" ]; then login_code="000"; fi
  login_body="$(cat "${login_body_file}" 2>/dev/null || true)"
  rm -f "${login_body_file}"
  token="$(json_get "${login_body}" access_token)"
  if [ -n "${token}" ]; then
    record "login" true "authenticated demo user (token not shown)"
  else
    login_error="$(json_safe_error_summary "${login_body}")"
    record "login" false "login failed via /api/v1/auth/login (http=${login_code}; ${login_error})"
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

# --- Check 4: create a tenant document for RAG grounding ---------------------
document_id=""
if [ -n "${token}" ]; then
  smoke_stamp="$(date -u +%Y%m%d%H%M%S)"
  doc_title="Smoke Sparkler Policy ${smoke_stamp}"
  doc_text="Smoke policy: sparkler exits are allowed only in the garden courtyard when a safety attendant is booked."
  doc_payload="$(json_payload \
    title "${doc_title}" \
    document_type "faq" \
    content_text "${doc_text}")"
  doc_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/documents" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${doc_payload}" 2>/dev/null || true)"
  document_id="$(json_get "${doc_body}" id)"
  if [ -n "${document_id}" ]; then
    record "document_create" true "created tenant document id=${document_id}"
  else
    record "document_create" false "document creation failed"
  fi
else
  record "document_create" false "skipped: no auth token"
fi

# --- Check 5: supported suggested reply with sources -------------------------
supported_conversation_id=""
supported_reply_id=""
if [ -n "${token}" ] && [ -n "${document_id}" ]; then
  supported_msg_payload="$(json_payload \
    client_name "Smoke Supported Client" \
    body "Are sparkler exits allowed in the garden courtyard?")"
  supported_msg_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/simulator/messages" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${supported_msg_payload}" 2>/dev/null || true)"
  supported_conversation_id="$(json_get "${supported_msg_body}" conversation_id)"
  if [ -n "${supported_conversation_id}" ]; then
    supported_reply_body="$(curl -s -X POST \
      "${API_BASE_URL}/api/v1/conversations/${supported_conversation_id}/suggested-reply" \
      -H "Authorization: Bearer ${token}" 2>/dev/null || true)"
    supported_reply_id="$(json_get "${supported_reply_body}" id)"
    supported="$(json_get "${supported_reply_body}" answer_supported)"
    source_count="$(json_len "${supported_reply_body}" rag_sources)"
    source_document_id="$(json_get "${supported_reply_body}" rag_sources.0.document_id)"
    if [ -n "${supported_reply_id}" ] \
      && [ "${supported}" = "true" ] \
      && [ "${source_count}" -gt 0 ] \
      && [ "${source_document_id}" = "${document_id}" ]; then
      record "suggested_reply_supported" true "reply id=${supported_reply_id} grounded in created document"
    else
      record "suggested_reply_supported" false "expected supported reply with source document ${document_id}"
    fi
  else
    record "suggested_reply_supported" false "supported simulator message was not created"
  fi
else
  record "suggested_reply_supported" false "skipped: missing auth token or document"
fi

# --- Check 6: unsupported suggested reply refuses without sources ------------
unsupported_reply_id=""
if [ -n "${token}" ]; then
  unsupported_msg_payload="$(json_payload \
    client_name "Smoke Unsupported Client" \
    body "Can you book our honeymoon flight to Paris?")"
  unsupported_msg_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/simulator/messages" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${unsupported_msg_payload}" 2>/dev/null || true)"
  unsupported_conversation_id="$(json_get "${unsupported_msg_body}" conversation_id)"
  if [ -n "${unsupported_conversation_id}" ]; then
    unsupported_reply_body="$(curl -s -X POST \
      "${API_BASE_URL}/api/v1/conversations/${unsupported_conversation_id}/suggested-reply" \
      -H "Authorization: Bearer ${token}" 2>/dev/null || true)"
    unsupported_reply_id="$(json_get "${unsupported_reply_body}" id)"
    unsupported="$(json_get "${unsupported_reply_body}" answer_supported)"
    unsupported_source_count="$(json_len "${unsupported_reply_body}" rag_sources)"
    refusal_reason="$(json_get "${unsupported_reply_body}" refusal_reason)"
    if [ -n "${unsupported_reply_id}" ] \
      && [ "${unsupported}" = "false" ] \
      && [ "${unsupported_source_count}" -eq 0 ] \
      && [ -n "${refusal_reason}" ]; then
      record "suggested_reply_refusal" true "unsupported reply refused without sources"
    else
      record "suggested_reply_refusal" false "unsupported reply did not refuse cleanly"
    fi
  else
    record "suggested_reply_refusal" false "unsupported simulator message was not created"
  fi
else
  record "suggested_reply_refusal" false "skipped: no auth token"
fi

# --- Check 7: audit log includes AI flow events ------------------------------
if [ -n "${token}" ]; then
  audit_body="$(curl -s "${API_BASE_URL}/api/v1/audit-logs?limit=200" \
    -H "Authorization: Bearer ${token}" 2>/dev/null || true)"
  has_generated="$(json_audit_has_reply_event \
    "${audit_body}" "suggested_reply.generated" "${supported_reply_id}")"
  has_refusal="$(json_audit_has_reply_event \
    "${audit_body}" "suggested_reply.refused_no_source" "${unsupported_reply_id}")"
  if [ "${has_generated}" = "true" ] && [ "${has_refusal}" = "true" ]; then
    record "audit_ai_flow" true "found suggested reply generated and refusal audit events"
  else
    record "audit_ai_flow" false "missing suggested reply generated/refusal audit events"
  fi
else
  record "audit_ai_flow" false "skipped: no auth token"
fi

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
