#!/bin/sh
set -e

# Sanitize API_UPSTREAM if empty, missing host (e.g. "http://:"), or invalid
if [ -z "$API_UPSTREAM" ] || echo "$API_UPSTREAM" | grep -qE "(^:|://:|://$|http://:$|https://:$)"; then
  echo "[entrypoint] WARNING: API_UPSTREAM is empty or malformed ('$API_UPSTREAM')."
  echo "[entrypoint] Falling back to default: http://127.0.0.1:5000"
  export API_UPSTREAM="http://127.0.0.1:5000"
fi

# Ensure scheme is present
case "$API_UPSTREAM" in
  http://*|https://*) ;;
  *) export API_UPSTREAM="http://$API_UPSTREAM" ;;
esac

echo "[entrypoint] Active API_UPSTREAM: $API_UPSTREAM"

exec /docker-entrypoint.sh "$@"
