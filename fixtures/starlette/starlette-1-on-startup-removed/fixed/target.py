from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

cache = {}


async def warm_cache():
    cache["greeting"] = "hello"


async def greet(request):
    return JSONResponse({"greeting": cache.get("greeting")})


@asynccontextmanager
async def lifespan(app):
    await warm_cache()
    yield


app = Starlette(routes=[Route("/", greet)], lifespan=lifespan)
