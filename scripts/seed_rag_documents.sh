#!/usr/bin/env bash
#
# Seed the demo RAG document packs into a running EventSense AI API.
#
# Logs in as each demo tenant manager and uploads that tenant's markdown
# documents through POST /api/v1/documents. The documents live under
# demo_data/rag_documents/<tenant>/ and are intentionally different between
# tenants so tenant-scoped RAG isolation can be demonstrated.
#
# Usage:
#   scripts/seed_rag_documents.sh
#   API_BASE_URL=http://localhost:8000 scripts/seed_rag_documents.sh
#
# Environment:
#   API_BASE_URL   Base URL of the running API (default: http://localhost:8088)
#
# Duplicate handling:
#   Before uploading, the script lists existing documents and skips any whose
#   title already exists for that tenant. This makes the script safe to re-run.
#   (Matching is by exact title; if you change a document's content you should
#   archive/replace it through the API rather than relying on this script.)
#
# Notes / assumptions:
#   - Login endpoint is POST /auth/token with {email, password, tenant_slug}.
#   - "pricing_packages.md" is uploaded with document_type "package" because the
#     backend DocumentType enum has no "pricing_package" value (it exposes
#     "pricing" and "package"). "package" is the closest valid value.
#   - Requires python3 (used only to build/parse JSON safely; no jq dependency).
#
set -u

API_BASE_URL="${API_BASE_URL:-http://localhost:8088}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS_ROOT="${REPO_ROOT}/demo_data/rag_documents"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but was not found on PATH." >&2
  exit 1
fi

# --- small helpers -----------------------------------------------------------

# Read a top-level string field from a JSON blob.
json_get() { # json key
  printf '%s' "$1" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); v=d.get('$2'); print('' if v is None else v)
except Exception:
    print('')"
}

# Return 'yes' if a document with the given exact title exists in a JSON array.
title_exists() { # json_array title
  TITLE="$2" python3 -c "import sys,json,os
try:
    arr=json.load(sys.stdin)
    want=os.environ['TITLE']
    print('yes' if any(d.get('title')==want for d in arr) else 'no')
except Exception:
    print('no')" <<<"$1"
}

# Build a DocumentCreate JSON body from a file's contents (handles escaping).
build_doc_payload() { # title document_type original_filename file_path
  TITLE="$1" DTYPE="$2" FNAME="$3" FPATH="$4" python3 -c "import json,os
with open(os.environ['FPATH'], 'r', encoding='utf-8') as fh:
    content = fh.read()
print(json.dumps({
    'title': os.environ['TITLE'],
    'document_type': os.environ['DTYPE'],
    'original_filename': os.environ['FNAME'],
    'content_text': content,
    'status': 'active',
}))"
}

TOKEN=""
TENANT_LABEL=""

login() { # tenant_slug email password label
  local slug="$1" email="$2" password="$3" label="$4"
  TENANT_LABEL="$label"
  echo ""
  echo "=== ${label} (${slug}) ==="
  echo "  -> logging in as ${email} ..."
  local payload
  payload="$(E="$email" P="$password" T="$slug" python3 -c "import json,os
print(json.dumps({'email':os.environ['E'],'password':os.environ['P'],'tenant_slug':os.environ['T']}))")"
  local body
  body="$(curl -s -X POST "${API_BASE_URL}/auth/token" \
    -H 'Content-Type: application/json' -d "${payload}" 2>/dev/null || true)"
  TOKEN="$(json_get "${body}" access_token)"
  if [ -z "${TOKEN}" ]; then
    echo "  [FAIL] login failed for ${slug} (no access_token returned)." >&2
    echo "         Check the API is running at ${API_BASE_URL} and the credentials are seeded." >&2
    return 1
  fi
  echo "  [OK] logged in (token not shown)."
  return 0
}

# Cache of existing document titles for the current tenant.
EXISTING_DOCS_JSON="[]"

load_existing_docs() {
  EXISTING_DOCS_JSON="$(curl -s "${API_BASE_URL}/api/v1/documents" \
    -H "Authorization: Bearer ${TOKEN}" 2>/dev/null || echo '[]')"
  # Guard against error bodies that are not arrays.
  case "$(printf '%s' "${EXISTING_DOCS_JSON}" | head -c 1)" in
    "[") : ;;
    *) EXISTING_DOCS_JSON="[]" ;;
  esac
}

upload_doc() { # title document_type file_path
  local title="$1" dtype="$2" fpath="$3"
  local fname
  fname="$(basename "$fpath")"

  if [ ! -f "$fpath" ]; then
    echo "  [FAIL] missing file: ${fpath}" >&2
    return 1
  fi

  if [ "$(title_exists "${EXISTING_DOCS_JSON}" "${title}")" = "yes" ]; then
    echo "  [SKIP] already exists: \"${title}\""
    return 0
  fi

  local payload code body
  payload="$(build_doc_payload "${title}" "${dtype}" "${fname}" "${fpath}")"
  body="$(curl -s -o /tmp/seed_rag_doc.$$ -w '%{http_code}' \
    -X POST "${API_BASE_URL}/api/v1/documents" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "${payload}" 2>/dev/null || echo 000)"
  code="${body}"
  body="$(cat /tmp/seed_rag_doc.$$ 2>/dev/null || true)"
  rm -f /tmp/seed_rag_doc.$$

  if [ "${code}" = "201" ]; then
    local doc_id
    doc_id="$(json_get "${body}" id)"
    echo "  [OK] uploaded \"${title}\" (${dtype}) id=${doc_id}"
    return 0
  fi

  echo "  [FAIL] upload failed for \"${title}\" (HTTP ${code})" >&2
  echo "         response: ${body}" >&2
  return 1
}

# filename -> "title|document_type". Order controls upload order.
DOC_TITLES=(
  "pricing_packages.md|%TENANT% Pricing & Packages|package"
  "deposit_policy.md|%TENANT% Deposit Policy|deposit_policy"
  "cancellation_policy.md|%TENANT% Cancellation Policy|cancellation_policy"
  "guest_count_policy.md|%TENANT% Guest Count Policy|service_description"
  "services_faq.md|%TENANT% FAQ|faq"
  "contract_terms.md|%TENANT% Contract Terms|contract_terms"
)

seed_tenant() { # tenant_dir title_prefix
  local dir="$1" prefix="$2"
  load_existing_docs
  local failures=0
  local entry filename title dtype
  for entry in "${DOC_TITLES[@]}"; do
    filename="${entry%%|*}"
    local rest="${entry#*|}"
    title="${rest%%|*}"
    dtype="${rest#*|}"
    title="${title//%TENANT%/${prefix}}"
    upload_doc "${title}" "${dtype}" "${DOCS_ROOT}/${dir}/${filename}" || failures=$((failures + 1))
  done
  return "${failures}"
}

# --- run ---------------------------------------------------------------------

echo "Seeding RAG demo documents into ${API_BASE_URL}"
echo "Documents source: ${DOCS_ROOT}"

OVERALL_FAIL=0

if login "elegant-weddings" "admin@elegant-weddings.demo" "demo-password-1" "Elegant Weddings"; then
  seed_tenant "elegant_weddings" "Elegant Weddings" || OVERALL_FAIL=1
else
  OVERALL_FAIL=1
fi

if login "royal-events-agency" "admin@royal-events.demo" "demo-password-2" "Royal Events Agency"; then
  seed_tenant "royal_events" "Royal Events" || OVERALL_FAIL=1
else
  OVERALL_FAIL=1
fi

echo ""
if [ "${OVERALL_FAIL}" = "0" ]; then
  echo "=> SEED COMPLETE (all documents uploaded or already present)"
  exit 0
else
  echo "=> SEED FINISHED WITH ERRORS (see [FAIL] lines above)" >&2
  exit 1
fi
