Here is the consolidated formal **BNF** for **JSON-RPC 2.0** provided as a single code block, followed by the separate explanations of the protocol's components.

```bnf
<json_rpc_message>    ::= <unit_object> | <batch_request>

<batch_request>       ::= "[" <unit_object> { "," <unit_object> } "]"

<unit_object>         ::= <request_object> | <notification_object> | 
                          <response_object> | <error_object>

<request_object>      ::= "{" <jsonrpc_ver> "," <method> [ "," <params> ] "," <id> "}"

<notification_object> ::= "{" <jsonrpc_ver> "," <method> [ "," <params> ] "}"

<response_object>     ::= "{" <jsonrpc_ver> "," <result> "," <id> "}"

<error_object>        ::= "{" <jsonrpc_ver> "," <error_body> "," <id> "}"

<jsonrpc_ver>         ::= '"jsonrpc"' ":" '"2.0"'

<method>              ::= '"method"' ":" <string>

<params>              ::= '"params"' ":" ( <json_array> | <json_object> )

<id>                  ::= '"id"' ":" ( <string> | <number> | "null" )

<result>              ::= '"result"' ":" <json_value>

<error_body>          ::= '"error"' ":" "{" <code_member> "," <msg_member> [ "," <data_member> ] "}"

<code_member>         ::= '"code"' ":" <integer>

<msg_member>          ::= '"message"' ":" <string>

<data_member>         ::= '"data"' ":" <json_value>

<json_value>          ::= <string> | <number> | <json_object> | <json_array> | 
                          "true" | "false" | "null"

<json_object>         ::= "{" [ <member> { "," <member> } ] "}"

<member>              ::= <string> ":" <json_value>

<json_array>          ::= "[" [ <json_value> { "," <json_value> } ] "]"

<string>              ::= '"' { <character> } '"'

<number>              ::= [ "-" ] <digit_sequence> [ "." <digit_sequence> ]

<integer>             ::= [ "-" ] <digit_sequence>

<digit_sequence>      ::= <digit> { <digit> }

<digit>               ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"

```

---

## Explanations

### 1. Message Types

* **Request Object**: A call to a specific method that requires a response. It must include an `id`.
* **Notification Object**: A call that does not require a response. It is identified by the absence of the `id` member.
* **Response Object**: The successful output of a request. It must contain the `result` member and must not contain the `error` member.
* **Error Object**: The output when a request fails. It must contain the `error` member and must not contain the `result` member.
* **Batch**: An array containing multiple Request or Notification objects.

### 2. Core Members

* **jsonrpc**: A string specifying the version of the protocol. It must be exactly `"2.0"`.
* **method**: A string containing the name of the method to be invoked. Names beginning with `rpc.` are reserved for internal use.
* **params**: A structured value (Object or Array) containing the arguments for the method.
* **id**: An identifier used to correlate the response with the request. It can be a string, a number, or null (though null is discouraged).
* **result**: The data returned by the server upon successful execution.

### 3. Error Handling

* **code**: A specific integer indicating the error type.
* `-32700`: Parse error (invalid JSON).
* `-32600`: Invalid Request.
* `-32601`: Method not found.
* `-32602`: Invalid params.
* `-32603`: Internal error.


* **message**: A concise, human-readable summary of the error.
* **data**: An optional member containing additional primitive or structured information about the error (e.g., stack traces).

### 4. JSON Primitives

* **String**: A sequence of characters wrapped in double quotes.
* **Number**: Standard decimal notation.
* **Object/Array**: The primary containers for key-value pairs and ordered lists, respectively.

