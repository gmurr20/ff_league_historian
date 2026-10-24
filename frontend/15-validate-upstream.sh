#!/bin/sh
# frontend/15-validate-upstream.sh - Validate & sanitize API_UPSTREAM before NGINX envsubst

# Detect empty, missing host (e.g. "http://:5000"), or truncated schemes
if [ -z "$API_UPSTREAM" ] || echo "$API_UPSTREAM" | grep -qE "(^:|://:|://$)" || [ "$API_UPSTREAM" = "http://" ] || [ "$API_UPSTREAM" = "https://" ]; then
  echo "[validate-upstream] WARNING: API_UPSTREAM is empty or malformed ('$API_UPSTREAM')."
  echo "[validate-upstream] Falling back to default: http://127.0.0.1:5000"
  export API_UPSTREAM="http://127.0.0.1:5000"
fi

# Ensure scheme is present
case "$API_UPSTREAM" in
  http://*|https://*) ;;
  *) export API_UPSTREAM="http://$API_UPSTREAM" ;;
esac

echo "[validate-upstream] Configured API_UPSTREAM: $API_UPSTREAM"
