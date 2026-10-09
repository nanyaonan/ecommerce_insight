import pytest
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