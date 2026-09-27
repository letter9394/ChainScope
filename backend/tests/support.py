from typing import Any

from fastapi.testclient import TestClient


class CsrfTestClient(TestClient):
    """Test client that behaves like the browser API wrapper for unsafe requests."""

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any):
        headers = dict(kwargs.pop("headers", None) or {})
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and str(url).startswith("/api/"):
            has_csrf_header = any(key.lower() == "x-csrf-token" for key in headers)
            if not has_csrf_header:
                csrf_response = TestClient.request(self, "GET", "/api/auth/csrf")
                csrf_response.raise_for_status()
                headers["X-CSRF-Token"] = csrf_response.json()["csrf_token"]
        return TestClient.request(self, method, url, *args, headers=headers, **kwargs)
