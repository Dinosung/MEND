<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our async Q&A service calls Claude and also tracks how close we are to our rate limit.
Please write `target.py` with an async function `ask(client, question)`, where `client` is an
`anthropic.AsyncAnthropic` instance we pass in. Send the question to `claude-sonnet-4-6`
(up to 512 output tokens) and return a tuple `(answer_text, remaining)`: the text of the
reply, and the number of requests left in the current window as an `int`, taken from the
`anthropic-ratelimit-requests-remaining` header of that same API response.
