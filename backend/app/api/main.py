from fastapi import FastAPI

from app.api import (
    approval_routes,
    auth_routes,
    calendar_routes,
    notification_routes,
    onboarding_routes,
    run_routes,
    workspace_routes,
)
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(auth_routes.router)
app.include_router(workspace_routes.router)
app.include_router(run_routes.router)
app.include_router(approval_routes.router)
app.include_router(notification_routes.router)
app.include_router(onboarding_routes.router)
app.include_router(calendar_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}
