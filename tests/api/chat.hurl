POST {{api_origin}}/v1/chat/completions
Authorization: Bearer {{api_key}}
Content-Type: application/json
{
  "model": "{{model}}",
  "messages": [
    {"role": "user", "content": "Reply with exactly PONG and nothing else. /no_think"}
  ],
  "chat_template_kwargs": {"enable_thinking": false},
  "temperature": 0,
  "max_tokens": 128
}

HTTP 200
[Asserts]
jsonpath "$.choices[0].message.content" contains "PONG"
jsonpath "$.choices[0].message.content" not contains "<think>"
