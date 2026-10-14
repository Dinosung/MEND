from contextlib import asynccontextmanager

from fastapi import FastAPI

resources = {}


def open_pool():
    resources["db"] = "connected"


def close_pool():
    resources.pop("db", None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"db": resources.get("db")}
