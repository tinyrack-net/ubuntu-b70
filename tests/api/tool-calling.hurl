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
  "max_tokens": 128
}

HTTP 200
[Asserts]
jsonpath "$.choices[0].message.tool_calls[0].function.name" == "lookup_weather"
jsonpath "$.choices[0].message.tool_calls[0].function.arguments" contains "서울"

POST {{api_origin}}/v1/chat/completions
Authorization: Bearer {{api_key}}
Content-Type: application/json
{
  "model": "{{model}}",
  "messages": [
    {"role": "user", "content": "서울의 현재 기온을 조회해 줘."},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_weather",
          "type": "function",
          "function": {"name": "lookup_weather", "arguments": "{\"city\":\"서울\"}"}
        }
      ]
    },
    {"role": "tool", "tool_call_id": "call_weather", "content": "{\"temperature_c\":18}"}
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
  "chat_template_kwargs": {"enable_thinking": false},
  "temperature": 0,
  "max_tokens": 128
}

HTTP 200
[Asserts]
jsonpath "$.choices[0].message.content" contains "18"
jsonpath "$.choices[0].message.content" not contains "<think>"
