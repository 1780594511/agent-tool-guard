from conftest import sign_in

from toolguard.agent import run_task
from toolguard.models import Proposal, Turn


def test_api_identity_csrf_and_no_bypass(client):
    assert client.post("/api/gateway/call", json={}).status_code == 401
    sign_in(client)
    me = client.get("/api/session").json()
    assert me["user"]["role"] == "employee"
    payload = {
        "tool": "read_document",
        "arguments": {"document_id": "hr-001"},
        "idempotency_key": "api1",
        "role": "hr",
    }
    assert client.post("/api/gateway/call", json=payload).status_code == 422
    payload.pop("role")
    assert client.post("/api/gateway/call", json=payload).json()["reason"] == "RESOURCE_FORBIDDEN"
    assert client.post("/api/executor/read_document", json=payload).status_code in {404, 405}
    assert client.get("/api/documents/hr-001").status_code == 404
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/gateway/call", json=payload).status_code == 403


def test_ownership_and_privileged_pages(client):
    sign_in(client)
    result = client.post(
        "/api/tasks", json={"prompt": "创建工单：调查勒索软件", "provider": "mock", "request_key": "own"}
    ).json()
    assert result["status"] == "completed"
    assert len(client.get("/api/tickets").json()) == 1
    assert client.get("/api/evaluations").status_code == 403
    assert client.get("/api/admin/access").status_code == 403
    sign_in(client, "hr")
    assert client.get(f"/api/tasks/{result['id']}").status_code == 404
    assert client.get("/api/tickets").json() == []
    assert client.get("/api/audit?user_id=employee").json() == []


def test_mock_injected_document_blocked(client):
    sign_in(client)
    result = client.post(
        "/api/tasks", json={"prompt": "读取 pub-injection", "provider": "mock", "request_key": "attack"}
    ).json()
    assert result["status"] == "blocked"
    assert [r["status"] for r in result["calls"]] == ["succeeded", "denied"]
    assert result["calls"][-1]["reason"] == "RESOURCE_FORBIDDEN"


def test_policy_admin_schema_and_no_business_superuser(client):
    sign_in(client, "admin")
    view = client.get("/api/policy").json()
    assert not any(d["classification"] == "hr" for d in view["documents"])
    changed = view["policy"]
    changed["approval_required"] = []
    assert (
        client.put("/api/policy", json={"expected_version": view["version"], "policy": changed}).status_code
        == 422
    )


def test_unknown_fields_not_echoed_to_logs(client):
    sign_in(client)
    bad = client.post("/api/gateway/call", json={"secret": "sk-do-not-log-this"})
    assert bad.status_code == 422
    assert "sk-do-not-log-this" not in bad.text
    sign_in(client, "admin")
    assert "sk-do-not-log-this" not in client.get("/api/audit").text


def test_origin_body_limit_and_logout(client):
    sign_in(client)
    assert client.post("/api/auth/logout", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post("/api/tasks", content="x" * 70_000).status_code == 413
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/session").status_code == 401


def test_task_idempotency(client):
    sign_in(client)
    payload = {"prompt": "创建工单：设备申请", "provider": "mock", "request_key": "same"}
    first = client.post("/api/tasks", json=payload).json()
    again = client.post("/api/tasks", json=payload).json()
    assert first["id"] == again["id"]
    assert len(client.get("/api/tickets").json()) == 1
    payload["prompt"] = "创建工单：不同内容"
    assert client.post("/api/tasks", json=payload).status_code == 409


def test_model_has_no_permission_mutation_tools(db, tokens):
    class Hostile:
        model_id = "hostile-test"

        def next(self, *args, **kwargs):
            return Turn(calls=[Proposal("set_role", {"role": "hr"})])

    result = run_task(db, tokens["employee"], "anything", "mock", "hostile", model=Hostile())
    assert result["calls"][0]["reason"] == "UNKNOWN_TOOL"


def test_task_step_limit(db, tokens):
    class Endless:
        model_id = "loop-test"

        def next(self, *args, **kwargs):
            return Turn(calls=[Proposal("create_ticket", {"title": "loop", "body": "bounded"})])

    result = run_task(db, tokens["employee"], "loop", "mock", "loop", model=Endless())
    assert result["status"] == "limit_reached"
    assert result["steps"] == 6


def test_retrieval_after_permission_revocation(client):
    sign_in(client, "engineer")
    task = client.post(
        "/api/tasks", json={"prompt": "读取 rd-001", "provider": "mock", "request_key": "revoke"}
    ).json()
    assert task["calls"][0]["result"]["body"]
    sign_in(client, "admin")
    assert (
        client.post(
            "/api/admin/access", json={"user_id": "engineer", "document_id": "rd-001", "granted": False}
        ).status_code
        == 200
    )
    sign_in(client, "engineer")
    assert client.get(f"/api/tasks/{task['id']}").json()["calls"][0]["result"] is None


def test_nonfinite_json_is_rejected_and_audited(client):
    sign_in(client)
    response = client.post(
        "/api/gateway/call",
        content='{"tool":"read_document","arguments":{"document_id":NaN},"idempotency_key":"nan"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    events = client.get("/api/audit").json()
    assert any(e["reason"] == "INVALID_REQUEST_ENVELOPE" for e in events)
