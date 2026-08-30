#!/bin/sh
set -eu

base_url=
api_key_file=
container=
marker=
failure_threshold=2
state_file=/run/vllm-content-canary.failures

while [ "$#" -gt 0 ]; do
  case "$1" in
    --base-url) base_url=$2; shift 2 ;;
    --api-key-file) api_key_file=$2; shift 2 ;;
    --container) container=$2; shift 2 ;;
    --marker) marker=$2; shift 2 ;;
    --failure-threshold) failure_threshold=$2; shift 2 ;;
    --state-file) state_file=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

test -n "$base_url"
test -n "$api_key_file"
test -n "$container"
test -n "$marker"

api_key=$(tr -d '\r\n' < "$api_key_file")

authorized_get() {
  curl --config - <<EOF
silent
show-error
fail
max-time = 30
url = "$1"
header = "Authorization: Bearer $api_key"
EOF
}

failed=1
model=$(authorized_get "${base_url%/}/v1/models" 2>/dev/null | jq -er '.data[0].id' 2>/dev/null || true)
if [ -n "$model" ]; then
  payload=$(jq -nc \
    --arg model "$model" \
    --arg prompt "Reply with exactly $marker and nothing else." \
    '{model: $model, messages: [{role: "user", content: $prompt}], chat_template_kwargs: {enable_thinking: false}, temperature: 0, max_tokens: 128}')
  content=$(
    curl --config - \
      --header 'Content-Type: application/json' \
      --data-binary "$payload" <<EOF 2>/dev/null | jq -er '.choices[0].message.content // ""' 2>/dev/null || true
silent
show-error
fail
max-time = 120
url = "${base_url%/}/v1/chat/completions"
header = "Authorization: Bearer $api_key"
EOF
  )
  case "$content" in
    *"$marker"*) failed=0 ;;
  esac
fi

if [ "$failed" -eq 0 ]; then
  rm -f "$state_file"
  exit 0
fi

previous=0
if [ -r "$state_file" ]; then
  previous=$(cat "$state_file" 2>/dev/null || printf '0')
  case "$previous" in
    ''|*[!0-9]*) previous=0 ;;
  esac
fi
failures=$((previous + 1))
printf '%s\n' "$failures" > "$state_file"

if [ "$failures" -ge "$failure_threshold" ]; then
  docker restart "$container"
  rm -f "$state_file"
  echo "vLLM content canary restarted the unhealthy container"
else
  echo "vLLM content canary failed ($failures/$failure_threshold)"
fi
exit 1
