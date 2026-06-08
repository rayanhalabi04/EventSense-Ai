from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.api import auth as root_auth
from app.api.v1 import auth, conversations, inbox, messages, simulator, tenants
from app.core.exceptions import ForbiddenError, forbidden_error_handler


app = FastAPI(title="EventSense AI API")
app.add_exception_handler(ForbiddenError, forbidden_error_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"detail", "error_code"}.issubset(exc.detail):
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

app.include_router(root_auth.router, prefix="/auth", tags=["auth"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["tenants"])
app.include_router(tenants.admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(conversations.router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(messages.router, prefix="/api/v1/conversations", tags=["messages"])
app.include_router(simulator.router, prefix="/api/v1/simulator", tags=["simulator"])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["inbox"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
