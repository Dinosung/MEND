<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with `extract_invoice(client, text)`, where `client` is an
`anthropic.Anthropic` instance we pass in. It should ask Claude (model `claude-sonnet-4-6`)
to pull the vendor name and the total amount out of free-form invoice text and return a dict
`{"vendor": str, "total": float}`. Use Claude's structured outputs feature through the
client's beta messages API with a JSON schema (`vendor` string, `total` number, both
required, no extra keys), so the reply is guaranteed to be valid JSON, then parse it.
