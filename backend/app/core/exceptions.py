from fastapi import Request, status
from fastapi.responses import JSONResponse


class ForbiddenError(Exception):
    def __init__(self, code: str = "CROSS_TENANT_ACCESS") -> None:
        self.code = code


async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": "forbidden", "code": exc.code},
    )
