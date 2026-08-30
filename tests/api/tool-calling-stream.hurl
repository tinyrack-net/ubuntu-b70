POST {{api_origin}}/v1/chat/completions
Authorization: Bearer {{api_key}}
Content-Type: application/json
{
  "model": "{{model}}",
  "messages": [
    {"role": "user", "content": "서울의 현재 기온을 조회해 줘. 설명하지 말고 도구를 호출해."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "lookup_weather",
        "description": "도시의 현재 날씨를 조회한다.",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }
  ],
  "tool_choice": "required",
  "chat_template_kwargs": {"enable_thinking": false},
  "temperature": 0,
  "max_tokens": 128,
  "stream": true,
  "stream_options": {"include_usage": true}
}

HTTP 200
[Asserts]
body contains "\"name\":\"lookup_weather\""
body contains "서울"
body contains "\"finish_reason\":\"tool_calls\""
