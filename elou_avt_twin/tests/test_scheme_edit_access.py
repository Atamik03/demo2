import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from auth.deps import get_current_user, require_permission
from auth.models import Principal
from auth.store import ROLE_PERMISSIONS


@pytest.mark.parametrize("roles,permissions,expected", [
    (["administrator"], ["manage_scheme"], 200),
    (["instructor"], ["manage_scheme"], 403),
    (["operator"], [], 403),
    (["custom_editor"], ["manage_scheme"], 403),
    (["administrator"], [], 403),
])
def test_scheme_edit_requires_administrator(roles, permissions, expected):
    app = FastAPI()

    @app.post("/scheme", dependencies=[Depends(require_permission("manage_scheme"))])
    def save():
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: Principal(username="test", roles=roles, permissions=permissions)
    with TestClient(app) as client:
        assert client.post("/scheme").status_code == expected


def test_instructor_catalog_excludes_scheme_editing():
    assert "manage_scheme" not in ROLE_PERMISSIONS["instructor"]
