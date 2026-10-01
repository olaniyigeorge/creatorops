from fastapi import FastAPI

from app.api import auth_routes, workspace_routes
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(auth_routes.router)
app.include_router(workspace_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}
