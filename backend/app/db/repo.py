"""The only sanctioned way to touch tenant-owned rows.

Every query is filtered by workspace_id, `add` stamps it, and foreign keys that
point at other tenant tables are checked to belong to the same workspace, so a
caller cannot attach a row to another tenant's data by passing a guessed id.
"""

import uuid
from typing import Any, Generic, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base, TenantMixin

M = TypeVar("M", bound=TenantMixin)


class CrossTenantReference(ValueError):
    pass


def tenant_models() -> list[type]:
    return [
        m.class_
        for m in Base.registry.mappers
        if issubclass(m.class_, TenantMixin)
    ]


def _model_for_table(table_name: str) -> Optional[type]:
    for m in Base.registry.mappers:
        if m.local_table.name == table_name:
            return m.class_
    return None


class WorkspaceRepo(Generic[M]):
    def __init__(self, session: Session, model: Type[M], workspace_id: uuid.UUID):
        if not (isinstance(model, type) and issubclass(model, TenantMixin)):
            raise TypeError(f"{model} is not a tenant model")
        if workspace_id is None:
            raise ValueError("workspace_id is required")
        self.session = session
        self.model = model
        self.workspace_id = workspace_id

    def _select(self):
        return select(self.model).where(self.model.workspace_id == self.workspace_id)

    def get(self, id: uuid.UUID) -> Optional[M]:
        return self.session.scalar(self._select().where(self.model.id == id))

    def list(self, **filters: Any) -> list[M]:
        q = self._select()
        for key, value in filters.items():
            q = q.where(getattr(self.model, key) == value)
        return list(self.session.scalars(q))

    def add(self, **fields: Any) -> M:
        if "workspace_id" in fields:
            raise ValueError("workspace_id is set by the repository")
        self._check_references(fields)
        obj = self.model(workspace_id=self.workspace_id, **fields)
        self.session.add(obj)
        self.session.flush()
        return obj

    def delete(self, id: uuid.UUID) -> bool:
        obj = self.get(id)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.flush()
        return True

    def _check_references(self, fields: dict[str, Any]) -> None:
        for fk in self.model.__table__.foreign_keys:
            col = fk.parent
            value = fields.get(col.key)
            if value is None or col.key == "workspace_id":
                continue
            target = _model_for_table(fk.column.table.name)
            if target is None or not issubclass(target, TenantMixin):
                continue  # e.g. users: not tenant-owned
            owner = self.session.scalar(
                select(target.workspace_id).where(target.id == value)
            )
            if owner != self.workspace_id:
                raise CrossTenantReference(
                    f"{self.model.__name__}.{col.key} references a row outside this workspace"
                )
