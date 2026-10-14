LABELS = ("positive", "negative", "neutral")


def classify_sentiment(client, text):
    """Label a customer review as positive, negative or neutral (repeatable output)."""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5,
        temperature=0,
        system=f"Reply with exactly one word: {', '.join(LABELS)}.",
        messages=[{"role": "user", "content": text}],
    )
    label = message.content[0].text.strip().lower()
    return label if label in LABELS else "neutral"
