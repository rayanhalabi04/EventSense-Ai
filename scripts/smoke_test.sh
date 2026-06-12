#!/usr/bin/env bash
#
# Smoke test for the EventSense AI dockerized stack (Spec 017).
#
# Checks: /health readiness -> demo login -> classify a simulated message ->
# create a tenant document -> generate a grounded suggested reply -> verify an
# unsupported refusal -> verify audit logs -> run the dry-run focused agent
# (apply=false) on a risky message (recommends escalation, writes nothing) and
# confirm it skips a non-risky message.
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

json_sources_match() { # json document_id marker
  # True if any rag_source matches the created document id, or (failing that)
  # carries the unique smoke marker in its id/title/content. This keeps the
  # check strict (it must be *our* document) without depending on RAG ranking
  # the newly created doc at position 0 versus older similar smoke documents.
  JSON_INPUT="$1" python3 - "$2" "$3" <<'PY'
import json
import os
import sys

doc_id = sys.argv[1]
marker = sys.argv[2]
try:
    data = json.loads(os.environ.get("JSON_INPUT", ""))
    sources = data.get("rag_sources", []) if isinstance(data, dict) else []
    matched = False
    for src in sources:
        if not isinstance(src, dict):
            continue
        if doc_id and str(src.get("document_id")) == doc_id:
            matched = True
            break
        if marker:
            blob = " ".join(
                str(src.get(field, ""))
                for field in ("document_id", "document_title", "content")
            )
            if marker in blob:
                matched = True
                break
    print("true" if matched else "false")
except Exception:
    print("false")
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

json_audit_has_event_for_resource() { # json event_type resource_id
  JSON_INPUT="$1" python3 - "$2" "$3" <<'PY'
import json
import os
import sys

event_type = sys.argv[1]
resource_id = sys.argv[2]
try:
    items = json.loads(os.environ.get("JSON_INPUT", ""))
    print(
        "true"
        if any(
            item.get("event_type") == event_type
            and str(item.get("resource_id")) == resource_id
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
# Each run embeds a unique marker so the document just created is the one that
# strongly retrieves for the supported-reply check below, regardless of older
# similar smoke documents already in the database.
document_id=""
smoke_marker=""
if [ -n "${token}" ]; then
  smoke_stamp="$(date -u +%Y%m%d%H%M%S)"
  smoke_marker="SMOKE_POLICY_${smoke_stamp}_${RANDOM}"
  doc_title="Smoke Sparkler Policy ${smoke_marker}"
  doc_text="${smoke_marker}: sparkler exits are allowed only in the garden courtyard when a safety attendant is booked."
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
    body "Are sparkler exits allowed in the garden courtyard with a safety attendant (${smoke_marker})?")"
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
    sources_match="$(json_sources_match "${supported_reply_body}" "${document_id}" "${smoke_marker}")"
    if [ -n "${supported_reply_id}" ] \
      && [ "${supported}" = "true" ] \
      && [ "${source_count}" -gt 0 ] \
      && [ "${sources_match}" = "true" ]; then
      record "suggested_reply_supported" true "reply id=${supported_reply_id} grounded in created smoke document (${smoke_marker})"
    else
      record "suggested_reply_supported" false "expected supported reply grounded in ${smoke_marker} (document ${document_id})"
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

# --- Check 8: dry-run agent runs + recommends escalation for a risky message -
# The focused agent only runs for risky/complex intents and never writes here
# (apply=false). A complaint should run the agent and recommend escalation.
risky_conversation_id=""
risky_msg_id=""
if [ -n "${token}" ]; then
  risky_msg_payload="$(json_payload \
    client_name "Smoke Risky Client" \
    body "I am absolutely furious and disappointed. Your service was terrible and unacceptable.")"
  risky_msg_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/simulator/messages" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${risky_msg_payload}" 2>/dev/null || true)"
  risky_conversation_id="$(json_get "${risky_msg_body}" conversation_id)"
  risky_msg_id="$(json_get "${risky_msg_body}" message_id)"
  if [ -n "${risky_conversation_id}" ] && [ -n "${risky_msg_id}" ]; then
    agent_payload='{"message_id":"'"${risky_msg_id}"'","apply":false}'
    agent_file="/tmp/smoke_agent.$$"
    agent_code="$(curl -s -o "${agent_file}" -w '%{http_code}' \
      -X POST "${API_BASE_URL}/api/v1/conversations/${risky_conversation_id}/agent/run" \
      -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
      -d "${agent_payload}" 2>/dev/null)"
    if [ -z "${agent_code}" ]; then agent_code="000"; fi
    agent_body="$(cat "${agent_file}" 2>/dev/null || true)"
    rm -f "${agent_file}"
    agent_ran="$(json_get "${agent_body}" ran)"
    agent_escalate="$(json_get "${agent_body}" recommended_escalation.should_escalate)"
    agent_trigger="$(json_get "${agent_body}" trigger_intent)"
    if [ "${agent_code}" = "200" ] \
      && [ "${agent_ran}" = "true" ] \
      && [ "${agent_escalate}" = "true" ]; then
      record "agent_dry_run_risky" true "agent ran for intent=${agent_trigger}; recommended escalation (apply=false)"
    else
      record "agent_dry_run_risky" false "expected http=200 ran=true escalate=true (got http=${agent_code} ran=${agent_ran} escalate=${agent_escalate})"
    fi
  else
    record "agent_dry_run_risky" false "risky simulator message was not created"
  fi
else
  record "agent_dry_run_risky" false "skipped: no auth token"
fi

# --- Check 9: dry-run agent creates no tasks or escalations ------------------
if [ -n "${token}" ] && [ -n "${risky_conversation_id}" ]; then
  risky_detail_body="$(curl -s \
    "${API_BASE_URL}/api/v1/conversations/${risky_conversation_id}/detail" \
    -H "Authorization: Bearer ${token}" 2>/dev/null || true)"
  agent_task_count="$(json_len "${risky_detail_body}" tasks)"
  agent_esc_count="$(json_len "${risky_detail_body}" escalations)"
  if [ "${agent_task_count}" = "0" ] && [ "${agent_esc_count}" = "0" ]; then
    record "agent_dry_run_no_writes" true "dry-run created no tasks/escalations (tasks=0 escalations=0)"
  else
    record "agent_dry_run_no_writes" false "dry-run unexpectedly created records (tasks=${agent_task_count} escalations=${agent_esc_count})"
  fi
else
  record "agent_dry_run_no_writes" false "skipped: no auth token or risky conversation"
fi

# --- Check 10: audit log records the agent decision -------------------------
if [ -n "${token}" ] && [ -n "${risky_msg_id}" ]; then
  agent_audit_body="$(curl -s "${API_BASE_URL}/api/v1/audit-logs?limit=200" \
    -H "Authorization: Bearer ${token}" 2>/dev/null || true)"
  has_agent_event="$(json_audit_has_event_for_resource \
    "${agent_audit_body}" "agent.decision_created" "${risky_msg_id}")"
  if [ "${has_agent_event}" = "true" ]; then
    record "agent_audit_decision" true "found agent.decision_created audit event for the risky message"
  else
    record "agent_audit_decision" false "missing agent.decision_created audit event for the risky message"
  fi
else
  record "agent_audit_decision" false "skipped: no auth token or risky message"
fi

# --- Check 11: dry-run agent skips a non-risky message ----------------------
if [ -n "${token}" ]; then
  nonrisky_msg_payload="$(json_payload \
    client_name "Smoke Non-Risky Client" \
    body "How much does your gold wedding package cost?")"
  nonrisky_msg_body="$(curl -s -X POST "${API_BASE_URL}/api/v1/simulator/messages" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
    -d "${nonrisky_msg_payload}" 2>/dev/null || true)"
  nonrisky_conversation_id="$(json_get "${nonrisky_msg_body}" conversation_id)"
  nonrisky_msg_id="$(json_get "${nonrisky_msg_body}" message_id)"
  if [ -n "${nonrisky_conversation_id}" ] && [ -n "${nonrisky_msg_id}" ]; then
    nonrisky_agent_payload='{"message_id":"'"${nonrisky_msg_id}"'","apply":false}'
    nonrisky_agent_file="/tmp/smoke_agent_nonrisky.$$"
    nonrisky_agent_code="$(curl -s -o "${nonrisky_agent_file}" -w '%{http_code}' \
      -X POST "${API_BASE_URL}/api/v1/conversations/${nonrisky_conversation_id}/agent/run" \
      -H 'Content-Type: application/json' -H "Authorization: Bearer ${token}" \
      -d "${nonrisky_agent_payload}" 2>/dev/null)"
    if [ -z "${nonrisky_agent_code}" ]; then nonrisky_agent_code="000"; fi
    nonrisky_agent_body="$(cat "${nonrisky_agent_file}" 2>/dev/null || true)"
    rm -f "${nonrisky_agent_file}"
    nonrisky_ran="$(json_get "${nonrisky_agent_body}" ran)"
    nonrisky_skipped="$(json_get "${nonrisky_agent_body}" skipped_reason)"
    if [ "${nonrisky_agent_code}" = "200" ] \
      && [ "${nonrisky_ran}" = "false" ] \
      && [ "${nonrisky_skipped}" = "intent_not_in_trigger_set" ]; then
      record "agent_dry_run_non_risky" true "non-risky message skipped (skipped_reason=intent_not_in_trigger_set)"
    else
      record "agent_dry_run_non_risky" false "expected http=200 ran=false skipped_reason=intent_not_in_trigger_set (got http=${nonrisky_agent_code} ran=${nonrisky_ran} skipped=${nonrisky_skipped})"
    fi
  else
    record "agent_dry_run_non_risky" false "non-risky simulator message was not created"
  fi
else
  record "agent_dry_run_non_risky" false "skipped: no auth token"
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
