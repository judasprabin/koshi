from fastapi import FastAPI

from koshi.api.occupations import router as occupations_router

app = FastAPI(title="koshi", version="0.1.0", openapi_url="/v1/openapi.json", docs_url="/v1/docs")
app.include_router(occupations_router)


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
