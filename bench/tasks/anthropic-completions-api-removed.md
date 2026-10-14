<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with `suggest_title(client, notes)`, where `client` is an
`anthropic.Anthropic` instance we pass in. It should send the raw meeting notes to Claude
(model `claude-sonnet-4-6`) with a short prompt asking for a title, and return the model's
reply as a plain string with surrounding whitespace stripped. Keep it to a single API call.
