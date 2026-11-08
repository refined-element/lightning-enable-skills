#!/usr/bin/env bash
# claim.sh: the curl fallback for sell-with-lightning-address.
#
# Use it only when the MCP has no l402_producer(action="sell_url"). It sends the
# producer claim (GET/POST /api/producer/claim) with fixed flags, so the agent never
# retypes them and both phases always send the same body file.
#
# Usage:
#   claim.sh quote              GET the quote (free) into quote.json and print it
#   claim.sh phase1             POST body.json with no Authorization; 402 into challenge.json
#   claim.sh save-auth          read the payment's header value (L402 <macaroon>:<preimage>)
#                               from stdin into auth.header (0600)
#   claim.sh phase2             POST the same body.json with auth.header; 200 into
#                               response.json (0600); prints it with apiKey redacted
#   claim.sh store-key-file     write response.json's apiKey to
#                               ~/.lightning-enable/claim-<proxyId>.key (0600), replacing it
#   claim.sh status [KEYFILE]   GET /api/producer/claim/status with the key from KEYFILE,
#                               or from lightningEnableApiKey in ~/.lightning-enable/config.json
#   claim.sh clean              delete body.json, challenge.json, auth.header, response.json
#
# Environment: LE_API_BASE (default https://api.lightningenable.com),
#              LE_CLAIM_DIR (default ~/.lightning-enable/claim).
# Secrets (the macaroon and preimage, the API key) never go on a command line: headers
# are read from files or stdin with curl -H @file / -H @-.
set -euo pipefail
umask 077

BASE="${LE_API_BASE:-https://api.lightningenable.com}"
DIR="${LE_CLAIM_DIR:-$HOME/.lightning-enable/claim}"
CONFIG_DIR="$(dirname "$DIR")"
URL="$BASE/api/producer/claim"

die() { echo "claim.sh: $*" >&2; exit 1; }

redact_key() { sed -E 's/"apiKey"[[:space:]]*:[[:space:]]*"[^"]*"/"apiKey":"<stored in response.json; not shown>"/'; }

json_string() { # json_string FIELD FILE: first "FIELD":"value" in FILE
  sed -nE "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/p" "$2" | head -n 1
}

mkdir -p "$DIR"
chmod 700 "$DIR" 2>/dev/null || true

cmd="${1:-}"
case "$cmd" in
  quote)
    code=$(curl -sS "$URL" -o "$DIR/quote.json" -w "%{http_code}")
    echo "HTTP $code"
    cat "$DIR/quote.json"; echo
    ;;

  phase1)
    [ -f "$DIR/body.json" ] || die "no $DIR/body.json; write the claim body first"
    # Once a payment exists, a new phase 1 would mint a second invoice: refuse.
    [ -f "$DIR/auth.header" ] && die "auth.header exists: this claim is paid. Run phase2, never phase1 again."
    code=$(curl -sS -X POST "$URL" \
      -H "Content-Type: application/json" \
      --data-binary @"$DIR/body.json" \
      -o "$DIR/challenge.json" -w "%{http_code}")
    echo "HTTP $code"
    cat "$DIR/challenge.json"; echo
    ;;

  save-auth)
    IFS= read -r value || true
    case "$value" in
      "L402 "*:*) ;;
      *) die "expected the payment's header value, L402 <macaroon>:<preimage>, on stdin" ;;
    esac
    printf 'Authorization: %s\n' "$value" > "$DIR/auth.header"
    chmod 600 "$DIR/auth.header"
    echo "saved $DIR/auth.header"
    ;;

  phase2)
    [ -f "$DIR/body.json" ] || die "no $DIR/body.json; phase 2 needs the same body file phase 1 sent"
    [ -f "$DIR/auth.header" ] || die "no $DIR/auth.header; pay the 402, then run save-auth"
    code=$(curl -sS -X POST "$URL" \
      -H "Content-Type: application/json" \
      -H @"$DIR/auth.header" \
      --data-binary @"$DIR/body.json" \
      -o "$DIR/response.json" -w "%{http_code}") || code="000"
    chmod 600 "$DIR/response.json" 2>/dev/null || true
    echo "HTTP $code"
    [ -f "$DIR/response.json" ] && { redact_key < "$DIR/response.json"; echo; }
    ;;

  store-key-file)
    [ -f "$DIR/response.json" ] || die "no $DIR/response.json"
    key=$(json_string apiKey "$DIR/response.json")
    proxy=$(json_string proxyId "$DIR/response.json")
    [ -n "$key" ] || die "response.json has no apiKey (apiKey is null on a claim made with an existing account's key)"
    [ -n "$proxy" ] || die "response.json has no proxy.proxyId"
    safe=$(printf '%s' "$proxy" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9-' '-')
    out="$CONFIG_DIR/claim-$safe.key"
    printf '%s\n' "$key" > "$out"
    chmod 600 "$out"
    echo "stored $out"
    ;;

  status)
    if [ -n "${2:-}" ]; then
      key=$(head -n 1 "$2" | tr -d '\r\n')
    else
      [ -f "$CONFIG_DIR/config.json" ] || die "no $CONFIG_DIR/config.json; pass the key file"
      key=$(json_string lightningEnableApiKey "$CONFIG_DIR/config.json")
    fi
    [ -n "$key" ] || die "no API key found"
    code=$(printf 'X-API-Key: %s\n' "$key" | curl -sS "$URL/status" -H @- \
      -o "$DIR/status.json" -w "%{http_code}")
    echo "HTTP $code"
    cat "$DIR/status.json"; echo
    rm -f "$DIR/status.json"
    ;;

  clean)
    rm -f "$DIR/body.json" "$DIR/challenge.json" "$DIR/auth.header" "$DIR/response.json" "$DIR/quote.json"
    echo "cleaned $DIR"
    ;;

  *)
    sed -n '2,24p' "$0" >&2
    exit 2
    ;;
esac
