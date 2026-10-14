from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def health(request):
    return JSONResponse({"status": "ok"})


async def get_user(request):
    return JSONResponse({"id": request.path_params["user_id"]})


app = Starlette(
    routes=[
        Route("/health", health),
        Route("/users/{user_id:int}", get_user, methods=["GET"]),
    ]
)
