async def ask(client, question):
    """Answer a question and report how many requests are left in the rate-limit window."""
    raw = await client.messages.with_raw_response.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )
    message = await raw.parse()
    remaining = int(raw.headers["anthropic-ratelimit-requests-remaining"])
    return message.content[0].text, remaining
