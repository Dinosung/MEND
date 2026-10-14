<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our production hosts can reach the internet only through the corporate HTTP proxy. Please
write `target.py` with `make_client(api_key, proxy_url)` that returns an
`anthropic.Anthropic` client for that API key whose requests all go through the proxy at
`proxy_url` (for example `http://proxy.internal:3128`). Don't change process-wide
environment variables; the proxy should be a setting of this client only. The rest of our
code calls `client.messages.create(...)` on the returned client.
