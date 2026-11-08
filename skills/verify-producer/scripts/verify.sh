#!/usr/bin/env bash
# verify.sh: curl helpers for verify-producer, proxy ownership verification.
#
# Every subcommand takes plain words (a proxy id, a path, a number), so the agent never
# writes a quoted header, a JSON body, or the API key on a command line.
#
# Usage:
#   verify.sh state PROXY_ID                  GET /api/proxy/PROXY_ID/verification: the state and the
#                                             exact instructions for this proxy (never the token)
#   verify.sh token PROXY_ID [--reissue]      POST /api/proxy/PROXY_ID/verification/token; saves the token
#                                             to verify-PROXY_ID.token (0600) and prints the answer with
#                                             the token redacted. Refuses, before any request, when a token
#                                             file exists or the proxy is verified by a live check, unless
#                                             --reissue: a new token unverifies and unlists the proxy.
#   verify.sh token PROXY_ID --from-claim [FILE]
#                                             no request: copy verification.token from the claim response
#                                             (default: the claim fallback's response.json) into the token file
#   verify.sh write-well-known PROXY_ID PATH  write {"verify":"<token>"} to PATH (a file, or a web root
#                                             directory, which gets .well-known/lightning-enable.json); a
#                                             file that already lists other tokens keeps them, as an array
#   verify.sh verify PROXY_ID                 POST /api/proxy/PROXY_ID/verify once.
#                                             Exit 0 verified, 3 pending, 4 not verified, 1 error.
#   verify.sh poll PROXY_ID [ATTEMPTS]        verify up to ATTEMPTS times (default 5, at most 10); waits
#                                             retryAfterSeconds after a pending check and LE_POLL_INTERVAL
#                                             seconds after a failed one; stops at the first success
#   verify.sh list PROXY_ID                   PUT /api/proxy/PROXY_ID/manifest/settings with
#                                             manifestEnabled and manifestPubliclyListed true
#
# The API key comes from the file named by LE_KEY_FILE (first line), or from lightningEnableApiKey in
# ~/.lightning-enable/config.json. It goes to curl on stdin (-H @-), never on the command line.
#
# Environment: LE_API_BASE (default https://api.lightningenable.com),
#              LE_CONFIG_DIR (default ~/.lightning-enable; token files live here),
#              LE_CLAIM_DIR (default LE_CONFIG_DIR/claim, the claim fallback's state),
#              LE_KEY_FILE, LE_POLL_INTERVAL (default 60), LE_MAX_WAIT (default 120).
set -euo pipefail
umask 077

BASE="${LE_API_BASE:-https://api.lightningenable.com}"
CONFIG_DIR="${LE_CONFIG_DIR:-$HOME/.lightning-enable}"
CLAIM_DIR="${LE_CLAIM_DIR:-$CONFIG_DIR/claim}"
POLL_INTERVAL="${LE_POLL_INTERVAL:-60}"
MAX_WAIT="${LE_MAX_WAIT:-120}"
MAX_ATTEMPTS=10

die() { echo "verify.sh: $*" >&2; exit 1; }

is_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

# first_string FIELD FILE: the first "FIELD":"value" in FILE (escaped quotes kept as \").
first_string() {
  grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" "$2" 2>/dev/null | head -n 1 \
    | sed -E "s/^\"$1\"[[:space:]]*:[[:space:]]*\"//; s/\"\$//" || true
}

# first_value FIELD FILE: the first bare value (true, false, null, a number) of FIELD in FILE.
first_value() {
  grep -oE "\"$1\"[[:space:]]*:[[:space:]]*[A-Za-z0-9.]+" "$2" 2>/dev/null | head -n 1 \
    | sed -E "s/^\"$1\"[[:space:]]*:[[:space:]]*//" || true
}

redact_token() { sed -E 's/"token"[[:space:]]*:[[:space:]]*"[^"]*"/"token":"<saved to the token file; not shown>"/g'; }

check_proxy_id() {
  case "$1" in
    ''|-*|*[!A-Za-z0-9_-]*) die "proxy id must be letters, digits, '-' and '_' only (got '$1')" ;;
  esac
  [ "${#1}" -le 100 ] || die "proxy id is longer than 100 characters"
}

check_token() {
  case "$1" in
    ''|*[!A-Za-z0-9_-]*) die "the token must be letters, digits, '-' and '_' only" ;;
  esac
  [ "${#1}" -ge 16 ] && [ "${#1}" -le 128 ] || die "the token has an unexpected length"
}

token_file() { printf '%s/verify-%s.token' "$CONFIG_DIR" "$1"; }

save_token() { # save_token PROXY_ID TOKEN
  check_token "$2"
  mkdir -p "$CONFIG_DIR"
  chmod 700 "$CONFIG_DIR" 2>/dev/null || true
  printf '%s\n' "$2" > "$(token_file "$1")"
  chmod 600 "$(token_file "$1")"
  echo "saved the token to $(token_file "$1") (mode 600; not shown)"
}

read_token() { # read_token PROXY_ID
  local file
  file="$(token_file "$1")"
  [ -f "$file" ] || die "no $file; run: verify.sh token $1"
  head -n 1 "$file" | tr -d '\r\n'
}

load_key() {
  local key
  if [ -n "${LE_KEY_FILE:-}" ]; then
    [ -f "$LE_KEY_FILE" ] || die "LE_KEY_FILE names a file that does not exist"
    key=$(head -n 1 "$LE_KEY_FILE" | tr -d '\r\n')
  else
    [ -f "$CONFIG_DIR/config.json" ] || die "no API key: set LE_KEY_FILE to the key file, or store lightningEnableApiKey in $CONFIG_DIR/config.json"
    key=$(first_string lightningEnableApiKey "$CONFIG_DIR/config.json")
  fi
  [ -n "$key" ] || die "no API key found"
  printf '%s' "$key"
}

WORK=""
cleanup() { if [ -n "$WORK" ]; then rm -rf "$WORK"; fi; }
trap cleanup EXIT

# api METHOD PATH [JSON]: sets CODE, BODY (file) and HEADERS (file). The key goes on stdin.
api() {
  local method="$1" path="$2" json="${3:-}" key
  key=$(load_key) || exit 1
  [ -n "$WORK" ] || WORK=$(mktemp -d)
  BODY="$WORK/body.json"
  HEADERS="$WORK/headers.txt"
  : > "$BODY"; : > "$HEADERS"
  if [ -n "$json" ]; then
    CODE=$(printf 'X-API-Key: %s\n' "$key" | curl -sS -X "$method" "$BASE$path" -H @- \
      -H "Content-Type: application/json" --data-binary "$json" \
      -D "$HEADERS" -o "$BODY" -w "%{http_code}") || CODE="000"
  else
    CODE=$(printf 'X-API-Key: %s\n' "$key" | curl -sS -X "$method" "$BASE$path" -H @- \
      -D "$HEADERS" -o "$BODY" -w "%{http_code}") || CODE="000"
  fi
}

retry_after_header() {
  grep -i '^Retry-After:' "$HEADERS" 2>/dev/null | head -n 1 | tr -dc '0-9' || true
}

capped() { # capped SECONDS: SECONDS, at most MAX_WAIT, at least 1
  local s="$1"
  is_uint "$s" || s=1
  [ "$s" -ge 1 ] || s=1
  [ "$s" -le "$MAX_WAIT" ] || s="$MAX_WAIT"
  printf '%s' "$s"
}

# verify_once PROXY_ID: one POST verify; prints a summary; returns 0/3/4/1 and sets WAIT_HINT.
verify_once() {
  local verified pending retry method reason
  WAIT_HINT=""
  api POST "/api/proxy/$1/verify"
  echo "HTTP $CODE"
  case "$CODE" in
    200) ;;
    429) WAIT_HINT=$(retry_after_header); cat "$BODY"; echo; return 1 ;;
    *) cat "$BODY"; echo; return 1 ;;
  esac
  verified=$(first_value verified "$BODY")
  pending=$(first_value pending "$BODY")
  retry=$(first_value retryAfterSeconds "$BODY")
  method=$(first_string method "$BODY")
  reason=$(first_string reason "$BODY" | sed 's/\\"/"/g')
  if [ "$verified" = "true" ]; then
    echo "verified: true (method: $method)"
    return 0
  fi
  if [ "$pending" = "true" ]; then
    WAIT_HINT="$retry"
    echo "pending: the check ran out of time and recorded nothing; retry after ${retry:-a few} seconds"
    [ -n "$reason" ] && echo "reason: $reason"
    return 3
  fi
  echo "verified: false (failures: $(first_value failures "$BODY"))"
  [ -n "$reason" ] && echo "reason: $reason"
  return 4
}

cmd="${1:-}"
case "$cmd" in
  state)
    [ $# -eq 2 ] || die "usage: verify.sh state PROXY_ID"
    check_proxy_id "$2"
    api GET "/api/proxy/$2/verification"
    echo "HTTP $CODE"
    cat "$BODY"; echo
    [ "$CODE" = "200" ]
    ;;

  token)
    [ $# -ge 2 ] || die "usage: verify.sh token PROXY_ID [--reissue | --from-claim [FILE]]"
    check_proxy_id "$2"
    proxy="$2"; mode="${3:-}"
    case "$mode" in
      --from-claim)
        src="${4:-$CLAIM_DIR/response.json}"
        [ -f "$src" ] || die "no $src; issue a token instead: verify.sh token $proxy"
        tok=$(first_string token "$src")
        [ -n "$tok" ] || die "$src has no verification.token (a replayed claim carries none); issue one: verify.sh token $proxy"
        save_token "$proxy" "$tok"
        ;;
      ''|--reissue)
        if [ -z "$mode" ]; then
          [ -f "$(token_file "$proxy")" ] && die "$(token_file "$proxy") exists: you already hold a token. Publish it; to replace it, pass --reissue."
          api GET "/api/proxy/$proxy/verification"
          [ "$CODE" = "200" ] || { echo "HTTP $CODE"; cat "$BODY"; echo; exit 1; }
          if [ "$(first_value verified "$BODY")" = "true" ]; then
            m=$(first_string method "$BODY")
            case "$m" in
              grandfathered|platform) ;;
              *) die "this proxy is verified (method: $m). A new token unverifies and unlists it until it verifies again; pass --reissue only if the operator wants that." ;;
            esac
          fi
        fi
        api POST "/api/proxy/$proxy/verification/token"
        echo "HTTP $CODE"
        if [ "$CODE" = "200" ]; then
          tok=$(first_string token "$BODY")
          [ -n "$tok" ] || die "the answer carried no token"
          save_token "$proxy" "$tok"
        fi
        redact_token < "$BODY"; echo
        [ "$CODE" = "200" ]
        ;;
      *) die "unknown option '$mode'" ;;
    esac
    ;;

  write-well-known)
    [ $# -eq 3 ] || die "usage: verify.sh write-well-known PROXY_ID PATH"
    check_proxy_id "$2"
    tok=$(read_token "$2") || exit 1
    check_token "$tok"
    out="$3"
    if [ -d "$out" ]; then
      out="${out%/}/.well-known/lightning-enable.json"
    fi
    case "$out" in
      *lightning-enable.json) ;;
      *) die "PATH must be the web root directory or a file named lightning-enable.json" ;;
    esac
    mkdir -p "$(dirname "$out")"
    tokens=""
    if [ -f "$out" ]; then
      # Keep the tokens other proxies on this host already publish.
      tokens=$(grep -oE '"[A-Za-z0-9_-]{16,128}"' "$out" | tr -d '"' | grep -vx 'verify' || true)
    fi
    if printf '%s\n' "$tokens" | grep -qx -- "$tok"; then
      echo "$out already carries this proxy's token; nothing changed"
      exit 0
    fi
    tokens=$(printf '%s\n%s\n' "$tokens" "$tok" | sed '/^$/d')
    if [ "$(printf '%s\n' "$tokens" | wc -l | tr -d ' ')" = "1" ]; then
      json="{\"verify\":\"$tok\"}"
    else
      json="{\"verify\":[$(printf '%s\n' "$tokens" | sed 's/.*/"&"/' | paste -sd, -)]}"
    fi
    printf '%s\n' "$json" > "$out"
    chmod 644 "$out"  # served publicly by the web server
    echo "wrote $out ($(printf '%s\n' "$tokens" | wc -l | tr -d ' ') token(s)); deploy it so it is served at https://<target host>/.well-known/lightning-enable.json"
    ;;

  verify)
    [ $# -eq 2 ] || die "usage: verify.sh verify PROXY_ID"
    check_proxy_id "$2"
    set +e; verify_once "$2"; rc=$?; set -e
    exit "$rc"
    ;;

  poll)
    [ $# -ge 2 ] && [ $# -le 3 ] || die "usage: verify.sh poll PROXY_ID [ATTEMPTS]"
    check_proxy_id "$2"
    attempts="${3:-5}"
    is_uint "$attempts" && [ "$attempts" -ge 1 ] && [ "$attempts" -le "$MAX_ATTEMPTS" ] \
      || die "ATTEMPTS must be a whole number from 1 to $MAX_ATTEMPTS"
    is_uint "$POLL_INTERVAL" || die "LE_POLL_INTERVAL must be a whole number of seconds"
    is_uint "$MAX_WAIT" || die "LE_MAX_WAIT must be a whole number of seconds"
    i=1
    while :; do
      echo "attempt $i of $attempts"
      set +e; verify_once "$2"; rc=$?; set -e
      case "$rc" in
        0) exit 0 ;;
        3) wait_for=$(capped "${WAIT_HINT:-1}") ;;
        4) wait_for="$POLL_INTERVAL"; [ "$wait_for" -le "$MAX_WAIT" ] || wait_for="$MAX_WAIT" ;;
        *)
          if [ "$CODE" = "429" ]; then
            wait_for=$(capped "${WAIT_HINT:-$POLL_INTERVAL}")
          else
            exit 1
          fi
          ;;
      esac
      [ "$i" -lt "$attempts" ] || break
      echo "waiting ${wait_for}s"
      sleep "$wait_for"
      i=$((i + 1))
    done
    echo "not verified after $attempts attempt(s)"
    exit 4
    ;;

  list)
    [ $# -eq 2 ] || die "usage: verify.sh list PROXY_ID"
    check_proxy_id "$2"
    api PUT "/api/proxy/$2/manifest/settings" '{"manifestEnabled":true,"manifestPubliclyListed":true}'
    echo "HTTP $CODE"
    cat "$BODY"; echo
    [ "$CODE" = "200" ]
    ;;

  *)
    sed -n '2,35p' "$0" >&2
    exit 2
    ;;
esac
