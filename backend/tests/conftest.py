import pytest

from app.main import _auth_rate_limiter


@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    _auth_rate_limiter.clear()
    yield
    _auth_rate_limiter.clear()
