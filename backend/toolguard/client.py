"""Small reusable HTTP client. Agent code has no direct tool execution endpoint."""

import uuid

import httpx


class GuardClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.http = httpx.Client(base_url=base_url, timeout=75, trust_env=False)

    def login(self, username, password):
        response = self.http.post("/api/auth/login", json={"username": username, "password": password})
        response.raise_for_status()
        self.http.headers["X-CSRF-Token"] = response.json()["csrf"]

    def call(self, tool, arguments, *, idempotency_key=None, approval_id=None):
        payload = {
            "tool": tool,
            "arguments": arguments,
            "idempotency_key": idempotency_key or uuid.uuid4().hex,
        }
        if approval_id:
            payload["approval_id"] = approval_id
        response = self.http.post("/api/gateway/call", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self):
        self.http.close()
