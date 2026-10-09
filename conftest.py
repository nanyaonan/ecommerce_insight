import os
import pytest
from starlette.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://apple:apple@127.0.0.1:5432/ecommerce_insight")

from app.main import app

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client

from app.main import app,get_current_user,Users

@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: Users(
        id=777, username="test_admin",is_admin=True
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def as_normal():
    app.dependency_overrides[get_current_user] = lambda: Users(
        id=888, username="test_normal",is_admin=False
    )
    yield
    app.dependency_overrides.clear()

