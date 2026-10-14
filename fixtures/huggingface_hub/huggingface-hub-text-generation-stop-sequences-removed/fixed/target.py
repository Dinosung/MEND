def complete_function(client, code):
    """Complete a Python function body; stop at the first blank line."""
    completion = client.text_generation(
        code,
        max_new_tokens=128,
        stop=["\n\n"],
    )
    return completion.split("\n\n")[0]
