#!/usr/bin/env bash

# Starts the repository's local Supabase project and refreshes only the
# Supabase/database values owned by this script. Existing application settings
# in backend/.env remain intact.
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly BACKEND_ENV="$REPO_ROOT/backend/.env"
readonly BACKEND_DOCKER_ENV="$REPO_ROOT/backend/.env.docker"
readonly BACKEND_EXAMPLE="$REPO_ROOT/backend/.env.example"
readonly FRONTEND_ENV="$REPO_ROOT/frontend/.env.local"
readonly FRONTEND_EXAMPLE="$REPO_ROOT/frontend/.env.example"
readonly STATUS_FILE="$(mktemp "${TMPDIR:-/tmp}/supabase-status.XXXXXX")"

cleanup() {
  # The status file contains local Supabase credentials, so remove it as soon as
  # the script exits.
  rm -f -- "$STATUS_FILE"
}
trap cleanup EXIT

require_command() {
  # Fail early with a clear message if the Supabase CLI is not installed.
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

status_value() {
  # Read one KEY=value entry from `supabase status --output env` without printing
  # the full credential set to the terminal.
  local key="$1"
  local value

  value="$({ awk -F= -v requested_key="$key" '$1 == requested_key { sub(/^[^=]*=/, ""); print; exit }' "$STATUS_FILE"; } | sed -e 's/^"//' -e 's/"$//')"

  if [[ -z "$value" ]]; then
    printf 'Local Supabase status did not provide %s.\n' "$key" >&2
    exit 1
  fi

  printf '%s' "$value"
}

write_environment_file() {
  # Rewrite an env file while preserving settings this script does not own. That
  # lets developers keep local app/logging/CORS values across Supabase refreshes.
  local destination="$1"
  local fallback="$2"
  shift 2
  local source="$destination"
  local temporary_file
  local key
  local key_pattern=""

  if [[ ! -f "$source" ]]; then
    source="$fallback"
  fi

  temporary_file="$(mktemp "${destination}.XXXXXX")"
  for key in "$@"; do
    if [[ -n "$key_pattern" ]]; then
      key_pattern+="|"
    fi
    key_pattern+="$key"
  done

  awk -v keys="^([[:space:]]*(export[[:space:]]+)?)("$key_pattern")=" '
    $0 !~ keys { print }
  ' "$source" > "$temporary_file"

  printf '\n' >> "$temporary_file"
  mv -- "$temporary_file" "$destination"
}

append_setting() {
  # Append a single KEY=value pair after the old managed keys were stripped.
  local destination="$1"
  local key="$2"
  local value="$3"

  printf '%s=%s\n' "$key" "$value" >> "$destination"
}

require_command supabase

cd "$REPO_ROOT"
# Start the single local Supabase project used by both frontend and backend.
if ! supabase start >/dev/null 2>&1; then
  printf 'Unable to start the local Supabase project. Check Docker and the Supabase CLI, then retry.\n' >&2
  exit 1
fi

# Read local API/database URLs and anon key into a temporary file. The script
# then copies only the required values into ignored app env files.
if ! supabase status --output env > "$STATUS_FILE" 2>/dev/null; then
  printf 'Unable to read local Supabase configuration.\n' >&2
  exit 1
fi

readonly API_URL="$(status_value API_URL)"
readonly ANON_KEY="$(status_value ANON_KEY)"
readonly DB_URL="$(status_value DB_URL)"
# Containers cannot reach the host's 127.0.0.1, so Docker-specific env values
# replace localhost with Docker's host gateway name.
DOCKER_DB_URL="${DB_URL/127.0.0.1/host.docker.internal}"
DOCKER_API_URL="${API_URL/127.0.0.1/host.docker.internal}"

if [[ "$DOCKER_DB_URL" == "$DB_URL" ]]; then
  DOCKER_DB_URL="${DB_URL/localhost/host.docker.internal}"
fi

if [[ "$DOCKER_API_URL" == "$API_URL" ]]; then
  DOCKER_API_URL="${API_URL/localhost/host.docker.internal}"
fi

readonly DOCKER_DB_URL
readonly DOCKER_API_URL

write_environment_file "$BACKEND_ENV" "$BACKEND_EXAMPLE" \
  DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_AUTH_TIMEOUT_SECONDS
append_setting "$BACKEND_ENV" DATABASE_URL "$DB_URL"
append_setting "$BACKEND_ENV" SUPABASE_URL "$API_URL"
append_setting "$BACKEND_ENV" SUPABASE_ANON_KEY "$ANON_KEY"
append_setting "$BACKEND_ENV" SUPABASE_AUTH_TIMEOUT_SECONDS 5

write_environment_file "$BACKEND_DOCKER_ENV" "$BACKEND_ENV" \
  DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_AUTH_TIMEOUT_SECONDS
append_setting "$BACKEND_DOCKER_ENV" DATABASE_URL "$DOCKER_DB_URL"
append_setting "$BACKEND_DOCKER_ENV" SUPABASE_URL "$DOCKER_API_URL"
append_setting "$BACKEND_DOCKER_ENV" SUPABASE_ANON_KEY "$ANON_KEY"
append_setting "$BACKEND_DOCKER_ENV" SUPABASE_AUTH_TIMEOUT_SECONDS 5

write_environment_file "$FRONTEND_ENV" "$FRONTEND_EXAMPLE" \
  NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY
append_setting "$FRONTEND_ENV" NEXT_PUBLIC_SUPABASE_URL "$API_URL"
append_setting "$FRONTEND_ENV" NEXT_PUBLIC_SUPABASE_ANON_KEY "$ANON_KEY"

printf 'Local Supabase is running and local application configuration has been refreshed.\n'
