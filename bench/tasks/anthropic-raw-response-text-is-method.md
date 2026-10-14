<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
For compliance we must keep the exact response body the Claude API sent for every request.
Please write `target.py` with `ask_and_archive(client, question, path)`, where `client` is an
`anthropic.Anthropic` instance we pass in: send the question to `claude-sonnet-4-6` (up to
512 output tokens), write the raw JSON body of that HTTP response, exactly as received, to
the file at `path`, and return the text of Claude's reply.
