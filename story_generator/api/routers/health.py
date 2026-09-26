from fastapi import APIRouter

router = APIRouter(tags=["system"])


# HEAD too: uptime monitors (UptimeRobot's default) check with HEAD, which a
# GET-only route answers with 405, so the site looks down when it isn't. Left
# out of the OpenAPI schema, where it would duplicate the GET operation.
@router.get("/health")
@router.head("/health", include_in_schema=False)
def health_check() -> dict[str, str]:
    return {"status": "ok"}
