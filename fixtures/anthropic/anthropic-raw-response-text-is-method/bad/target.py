def ask_and_archive(client, question, path):
    """Ask Claude; keep the API's raw JSON body in `path`; return the reply text."""
    raw = client.messages.with_raw_response.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw.text)
    return raw.parse().content[0].text
