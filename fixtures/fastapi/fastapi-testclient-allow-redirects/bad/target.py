from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI()


@app.get("/old-docs")
def old_docs():
    return RedirectResponse("/docs", status_code=301)


def redirect_location(client, path):
    """Test helper: return where `path` redirects to, without following it."""
    response = client.get(path, allow_redirects=False)
    assert response.is_redirect
    return response.headers["location"]
