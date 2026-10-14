from fastapi import FastAPI

resources = {}


def open_pool():
    resources["db"] = "connected"


def close_pool():
    resources.pop("db", None)


app = FastAPI()
app.add_event_handler("startup", open_pool)
app.add_event_handler("shutdown", close_pool)


@app.get("/health")
def health():
    return {"db": resources.get("db")}
