from anthropic import AI_PROMPT, HUMAN_PROMPT


def suggest_title(client, notes):
    """One-line title for a set of meeting notes."""
    completion = client.completions.create(
        model="claude-sonnet-4-6",
        max_tokens_to_sample=30,
        prompt=f"{HUMAN_PROMPT} Write a short title for these notes:\n{notes}{AI_PROMPT}",
    )
    return completion.completion.strip()
