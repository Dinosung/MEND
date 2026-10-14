from starlette.applications import Starlette
from starlette.responses import JSONResponse

app = Starlette()


@app.route("/health")
async def health(request):
    return JSONResponse({"status": "ok"})


@app.route("/users/{user_id:int}", methods=["GET"])
async def get_user(request):
    return JSONResponse({"id": request.path_params["user_id"]})
