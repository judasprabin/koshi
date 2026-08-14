from fastapi import FastAPI

app = FastAPI(title="koshi", version="0.1.0", openapi_url="/v1/openapi.json", docs_url="/v1/docs")


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
