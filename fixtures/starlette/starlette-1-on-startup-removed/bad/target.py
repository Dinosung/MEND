from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

cache = {}


async def warm_cache():
    cache["greeting"] = "hello"


async def greet(request):
    return JSONResponse({"greeting": cache.get("greeting")})


app = Starlette(routes=[Route("/", greet)], on_startup=[warm_cache])
