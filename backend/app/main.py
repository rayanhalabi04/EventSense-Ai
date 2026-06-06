from fastapi import FastAPI

from app.api.v1 import auth, conversations, messages, simulator, tenants


app = FastAPI(title="EventSense AI API")

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["tenants"])
app.include_router(conversations.router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(messages.router, prefix="/api/v1/conversations", tags=["messages"])
app.include_router(simulator.router, prefix="/api/v1/simulator", tags=["simulator"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
