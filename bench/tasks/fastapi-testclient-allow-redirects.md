<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We moved our docs and need the old URL to redirect. Please write `target.py` with a FastAPI
`app` where `GET /old-docs` returns a 301 redirect to `/docs`. Also add a test helper
`redirect_location(client, path)` that, given a FastAPI TestClient, requests `path` WITHOUT
following the redirect, asserts the response is a redirect, and returns the `Location`
header value.
