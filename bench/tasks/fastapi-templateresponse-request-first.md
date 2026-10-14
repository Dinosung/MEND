<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Add a server-rendered profile page to our FastAPI app. Please write `target.py` with an
`app` where `GET /profile/{name}` renders a Jinja2 template `profile.html` and returns HTML.
Use FastAPI's Jinja2 templating support; to keep it self-contained, load the template from
an in-memory `jinja2.DictLoader` with `profile.html` = `<h1>Hello {{ name }}</h1>`.
