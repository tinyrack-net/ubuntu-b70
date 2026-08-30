GET {{api_origin}}/v1/models
Authorization: Bearer {{api_key}}

HTTP 200
[Asserts]
jsonpath "$.data[0].id" == "{{model}}"
