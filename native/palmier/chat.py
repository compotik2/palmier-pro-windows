import json
import os
import urllib.request


def converse(prompt, tools, model="gpt-4.1-mini"):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Set OPENAI_API_KEY before launching to use BYOK chat. External Codex via MCP needs no in-app API key.")
    declarations = [dict(type="function", name=t["name"], description=t["description"], parameters=t["inputSchema"])
                    for t in tools.list() if t["name"] not in ("manage_project", "import_media", "export_project")]
    allowed = {tool["name"] for tool in declarations}
    messages = [dict(role="system", content="You assist a filmmaker in Palmier Windows. Only supported tools are available. Never claim generation or unsupported effects work. External imports, exports and project switching require the desktop or an external MCP client."),
                dict(role="user", content=prompt)]
    transcript = []
    for _ in range(8):
        body = json.dumps(dict(model=model, input=messages, tools=declarations)).encode()
        request = urllib.request.Request("https://api.openai.com/v1/responses", data=body,
                                         headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError(f"OpenAI API returned HTTP {error.code}; check credentials, billing and model access") from error
        calls = []
        for item in result.get("output", []):
            messages.append(item)
            if item.get("type") == "function_call":
                calls.append(item)
            elif item.get("type") == "message":
                transcript.extend(c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text")
        if not calls:
            return "\n".join(transcript) or "The API returned no text."
        for call in calls:
            try:
                if call["name"] not in allowed:
                    raise ValueError("This operation requires the desktop or an external MCP client")
                output = tools.call(call["name"], json.loads(call["arguments"]))
            except Exception as error:
                output = dict(error=str(error))
            messages.append(dict(type="function_call_output", call_id=call["call_id"], output=json.dumps(output)))
    raise ValueError("Agent reached the 8-step limit; inspect the timeline before continuing")
