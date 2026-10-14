import json

SCHEMA = {
    "type": "object",
    "properties": {"vendor": {"type": "string"}, "total": {"type": "number"}},
    "required": ["vendor", "total"],
    "additionalProperties": False,
}


def extract_invoice(client, text):
    """Pull {"vendor": str, "total": float} out of free-form invoice text as a dict."""
    message = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": f"Extract the vendor and total:\n{text}"}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    return json.loads(message.content[0].text)
