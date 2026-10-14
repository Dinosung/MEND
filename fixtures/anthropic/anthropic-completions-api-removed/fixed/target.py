def suggest_title(client, notes):
    """One-line title for a set of meeting notes."""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=30,
        messages=[{"role": "user", "content": f"Write a short title for these notes:\n{notes}"}],
    )
    return message.content[0].text.strip()
