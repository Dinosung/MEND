import jinja2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

env = jinja2.Environment(loader=jinja2.DictLoader({"profile.html": "<h1>Hello {{ name }}</h1>"}))
templates = Jinja2Templates(env=env)
app = FastAPI()


@app.get("/profile/{name}", response_class=HTMLResponse)
def profile(request: Request, name: str):
    return templates.TemplateResponse("profile.html", {"request": request, "name": name})
