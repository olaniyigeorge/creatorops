import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.deps import WorkspaceContext, owner_ctx, workspace_ctx
from app.api.schemas import ActionOut, RunCreate, RunDetail, RunOut
from app.db.models import Action, Run
from app.db.repo import WorkspaceRepo
from app.tasks import dispatch
from app.tasks.runner import PARAMS_MODELS, WORKFLOWS

router = APIRouter(tags=["runs"])


@router.post("/workspaces/{workspace_id}/runs", response_model=RunOut, status_code=201)
def start_run(body: RunCreate, ctx: WorkspaceContext = Depends(owner_ctx)):
    if body.workflow not in WORKFLOWS:
        raise HTTPException(status_code=422, detail=f"Unknown workflow '{body.workflow}'")
    params = body.params
    model = PARAMS_MODELS.get(body.workflow)
    if model is not None:
        try:
            params = model(**params).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False))
    elif params:
        raise HTTPException(status_code=422, detail=f"Workflow '{body.workflow}' takes no params")
    run = WorkspaceRepo(ctx.db, Run, ctx.workspace.id).add(
        workflow=body.workflow, params_json=params
    )
    ctx.db.commit()
    dispatch.enqueue_run(ctx.workspace.id, run.id)
    ctx.db.refresh(run)
    return run


@router.get("/workspaces/{workspace_id}/runs", response_model=list[RunOut])
def list_runs(ctx: WorkspaceContext = Depends(workspace_ctx)):
    runs = WorkspaceRepo(ctx.db, Run, ctx.workspace.id).list()
    return sorted(runs, key=lambda r: r.created_at, reverse=True)


@router.get("/workspaces/{workspace_id}/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, ctx: WorkspaceContext = Depends(workspace_ctx)):
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")
    run = WorkspaceRepo(ctx.db, Run, ctx.workspace.id).get(rid)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    actions = WorkspaceRepo(ctx.db, Action, ctx.workspace.id).list(run_id=run.id)
    actions.sort(key=lambda a: a.created_at)
    return RunDetail(
        **RunOut.model_validate(run).model_dump(),
        actions=[ActionOut.model_validate(a) for a in actions],
    )
