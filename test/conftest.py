import pytest
from app.main import app,get_current_user,Users

@pytest.fixture
def asadmin():
    app.dependency_overrides