<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We tag incoming customer reviews with Claude. Please write `target.py` with
`classify_sentiment(client, text)`, where `client` is an `anthropic.Anthropic` instance we
pass in: send the review text to Claude (model `claude-sonnet-4-6`) asking for a one-word
answer, and return `"positive"`, `"negative"` or `"neutral"` in lower case (fall back to
`"neutral"` for anything else). The same review should get the same label run after run, so
make the model's output as repeatable as you can.
