from fastapi import FastAPI
from routes import google_ads

app = FastAPI(title="Aconcaia Dash API", version="0.1.0")

app.include_router(google_ads.router, prefix="/google-ads")


@app.get("/health")
def health():
    return {"ok": True}
