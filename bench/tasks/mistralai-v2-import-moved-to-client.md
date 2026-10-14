<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our helpdesk wants a one-line summary on every support ticket, written by Mistral. Please
write `target.py` with two functions: `make_client(api_key)`, which returns a Mistral SDK
client for that key, and `summarize(client, ticket)`, where `client` is such a client passed
in by the caller. `summarize` should ask `mistral-small-latest` for a one-sentence summary of
the ticket text and return the model's answer as a string with surrounding whitespace
removed.
