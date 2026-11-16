import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from toolguard import executor
from toolguard.auth import GuardError
from toolguard.db import canonical, verify_audit
from toolguard.schemas import ToolRequest


def request(tool="read_document", args=None, key="k1", **extra):
    return ToolRequest(
        tool=tool,
        arguments=args if args is not None else {"document_id": "pub-001"},
        idempotency_key=key,
        **extra,
    )


def export(gateway, token, ids=None, key="exp", destination="inbox://compliance"):
    return gateway.invoke(
        token, request("export_report", {"document_ids": ids or ["pub-001"], "destination": destination}, key)
    )


def count(db, table):
    with db.transaction() as con:
        return con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


@pytest.mark.parametrize(
    "user,document,allowed",
    [
        ("employee", "pub-001", True),
        ("employee", "rd-001", False),
        ("employee", "hr-001", False),
        ("engineer", "rd-001", True),
        ("engineer", "rd-002", False),
        ("engineer", "hr-001", False),
        ("hr", "hr-001", True),
        ("hr", "hr-002", False),
        ("hr", "rd-001", False),
        ("approver", "hr-001", False),
        ("admin", "hr-001", False),
        ("employee", "missing", False),
    ],
)
def test_resource_permissions(gateway, db, tokens, user, document, allowed):
    result = gateway.invoke(tokens[user], request(args={"document_id": document}))
    assert (result["status"] == "succeeded") == allowed
    assert count(db, "read_receipts") == int(allowed)


@pytest.mark.parametrize(
    "tool,args,reason",
    [
        ("shell", {"command": "whoami"}, "UNKNOWN_TOOL"),
        ("read_document", {"document_id": "hr-001", "role": "hr"}, "INVALID_ARGUMENTS"),
        ("read_document", {"document_id": "hr-001", "user_id": "hr"}, "INVALID_ARGUMENTS"),
        ("read_document", {"document_id": ["pub-001"]}, "INVALID_ARGUMENTS"),
        ("read_document", {"document_id": "../../etc/passwd"}, "INVALID_ARGUMENTS"),
        ("create_ticket", {"title": "hello", "body": "world", "owner": "hr"}, "INVALID_ARGUMENTS"),
        (
            "export_report",
            {"document_ids": ["pub-001"], "destination": "https://attacker.invalid"},
            "DESTINATION_FORBIDDEN",
        ),
    ],
)
def test_fail_closed_inputs(gateway, db, tokens, tool, args, reason):
    result = gateway.invoke(tokens["employee"], request(tool, args))
    assert result["reason"] == reason
    assert not any(count(db, t) for t in ("tickets", "inbox", "read_receipts"))


def test_session_is_required(gateway):
    with pytest.raises(GuardError, match="SESSION_EXPIRED"):
        gateway.invoke("forged", request())


def test_approval_success_and_atomic_receipt(gateway, db, tokens):
    pending = export(gateway, tokens["engineer"], ["rd-001", "pub-001"])
    assert pending["status"] == "pending_approval"
    assert count(db, "inbox") == 0
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    done = gateway.resume(tokens["engineer"], pending["id"])
    assert done["status"] == "succeeded"
    with db.transaction() as con:
        approval = con.execute("SELECT * FROM approvals").fetchone()
        receipt = con.execute("SELECT * FROM inbox").fetchone()
        assert approval["status"] == "consumed"
        assert receipt["approval_id"] == approval["id"]
        assert json.loads(receipt["document_ids"]) == ["pub-001", "rd-001"]
        assert (
            con.execute(
                "SELECT COUNT(*) FROM audit WHERE event='execution' AND execution_status='succeeded'"
            ).fetchone()[0]
            == 1
        )
        assert verify_audit(con)["valid"]


def test_approval_does_not_grant_access(gateway, db, tokens):
    result = export(gateway, tokens["employee"], ["hr-001"])
    assert result["reason"] == "RESOURCE_FORBIDDEN"
    assert count(db, "approvals") == 0


def test_unprivileged_and_self_approval(gateway, db, tokens):
    pending = export(gateway, tokens["employee"])
    with pytest.raises(GuardError, match="APPROVAL_PERMISSION_REQUIRED"):
        gateway.decide(tokens["hr"], pending["approval_id"], "approve")
    with db.transaction() as con:
        con.execute("UPDATE users SET approval_scopes=? WHERE id='employee'", (canonical(["public"]),))
    with pytest.raises(GuardError, match="SELF_APPROVAL_FORBIDDEN"):
        gateway.decide(tokens["employee"], pending["approval_id"], "approve")
    assert count(db, "inbox") == 0


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("expire", "APPROVAL_EXPIRED"),
        ("revoke", "APPROVAL_REVOKED"),
        ("resource_version", "APPROVAL_BINDING_MISMATCH"),
        ("policy_version", "APPROVAL_BINDING_MISMATCH"),
        ("access_revoke", "RESOURCE_FORBIDDEN"),
        ("reviewer_revoke", "APPROVER_PERMISSION_REVOKED"),
    ],
)
def test_execution_rechecks(gateway, db, tokens, mutation, reason):
    pending = export(gateway, tokens["engineer"], ["rd-001"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    if mutation == "revoke":
        gateway.decide(tokens["engineer"], pending["approval_id"], "revoke")
    else:
        with db.transaction() as con:
            if mutation == "expire":
                con.execute("UPDATE approvals SET expires_at=?", (time.time() - 1,))
            elif mutation == "resource_version":
                con.execute("UPDATE documents SET version=version+1 WHERE id='rd-001'")
            elif mutation == "policy_version":
                con.execute("UPDATE policies SET version='p_changed'")
            elif mutation == "access_revoke":
                con.execute("DELETE FROM grants WHERE user_id='engineer' AND document_id='rd-001'")
                con.execute("UPDATE users SET revision=revision+1 WHERE id='engineer'")
            elif mutation == "reviewer_revoke":
                con.execute("UPDATE users SET approval_scopes='[]' WHERE id='approver'")
    done = gateway.resume(tokens["engineer"], pending["id"])
    assert done["reason"] == reason
    assert count(db, "inbox") == 0


def test_changed_arguments_invalidate_approval(gateway, db, tokens):
    pending = export(gateway, tokens["employee"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    changed = request(
        "export_report",
        {"document_ids": ["pub-002"], "destination": "inbox://compliance"},
        "changed",
        approval_id=pending["approval_id"],
    )
    result = gateway.invoke(tokens["employee"], changed)
    assert result["reason"] == "APPROVAL_BINDING_MISMATCH"
    assert gateway.resume(tokens["employee"], pending["id"])["reason"] == "APPROVAL_INVALIDATED"
    assert count(db, "inbox") == 0


def test_concurrent_approval_consumption_and_replay(gateway, db, tokens):
    pending = export(gateway, tokens["employee"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: gateway.resume(tokens["employee"], pending["id"]), range(8)))
    assert {r["status"] for r in results} == {"succeeded"}
    assert sum(not r["replayed"] for r in results) == 1
    assert count(db, "inbox") == 1
    reused = request(
        "export_report",
        {"document_ids": ["pub-001"], "destination": "inbox://compliance"},
        "reused",
        approval_id=pending["approval_id"],
    )
    assert gateway.invoke(tokens["employee"], reused)["reason"] == "APPROVAL_CONSUMED"


def test_ticket_idempotency_and_conflict(gateway, db, tokens):
    original = request("create_ticket", {"title": "security", "body": "密码泄漏调查"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: gateway.invoke(tokens["employee"], original), range(8)))
    assert len({r["result"]["ticket_id"] for r in results}) == 1
    changed = request("create_ticket", {"title": "different", "body": "new"})
    assert gateway.invoke(tokens["employee"], changed)["reason"] == "IDEMPOTENCY_CONFLICT"
    assert count(db, "tickets") == 1


def test_effect_failure_rolls_back_approval_and_allows_bounded_retry(gateway, db, tokens, monkeypatch):
    pending = export(gateway, tokens["employee"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    original = executor._execute

    def fail_after_write(con, permit):
        original(con, permit)
        raise RuntimeError("injected failure after business write")

    monkeypatch.setattr(executor, "_execute", fail_after_write)
    assert gateway.resume(tokens["employee"], pending["id"])["status"] == "failed"
    assert count(db, "inbox") == 0
    with db.transaction() as con:
        assert con.execute("SELECT status FROM approvals").fetchone()[0] == "approved"
    monkeypatch.setattr(executor, "_execute", original)
    assert gateway.resume(tokens["employee"], pending["id"])["status"] == "succeeded"
    assert count(db, "inbox") == 1


def test_retry_limit(gateway, db, tokens, monkeypatch):
    monkeypatch.setattr(executor, "_execute", lambda *args: (_ for _ in ()).throw(RuntimeError("fault")))
    req = request("create_ticket", {"title": "x", "body": "y"})
    assert gateway.invoke(tokens["employee"], req)["status"] == "failed"
    assert gateway.invoke(tokens["employee"], req)["status"] == "failed"
    assert gateway.invoke(tokens["employee"], req)["reason"] == "RETRY_LIMIT"
    assert count(db, "tickets") == 0


def test_authorization_exception_never_executes(gateway, db, tokens, monkeypatch):
    import toolguard.gateway as module

    monkeypatch.setattr(module, "authorize", lambda *args: (_ for _ in ()).throw(RuntimeError("policy bug")))
    assert gateway.invoke(tokens["employee"], request())["reason"] == "AUTHORIZATION_ERROR"
    assert count(db, "read_receipts") == 0


def test_corrupt_policy_fails_closed(gateway, db, tokens):
    with db.transaction() as con:
        con.execute("UPDATE policies SET body='{}'")
    assert gateway.invoke(tokens["employee"], request())["reason"] == "POLICY_ERROR"
    assert count(db, "read_receipts") == 0


def test_executor_has_no_unchecked_entry(db):
    with db.transaction() as con, pytest.raises(RuntimeError, match="EXECUTION_PERMIT_REQUIRED"):
        executor._execute(con, object())


def test_canonicalization_and_audit_privacy(gateway, db, tokens):
    result = gateway.invoke(
        tokens["employee"],
        request(
            "create_ticket", {"title": "密钥事件", "body": "secret=sk-local-secret alice@example.invalid"}
        ),
    )
    assert result["status"] == "succeeded"
    with db.transaction() as con:
        logs = canonical([dict(r) for r in con.execute("SELECT * FROM audit")])
        assert "sk-local-secret" not in logs and "alice@example.invalid" not in logs
        assert verify_audit(con)["valid"]


def test_audit_append_only(db):
    with db.transaction() as con:
        from toolguard.db import audit

        audit(con, event="test")
        with pytest.raises(Exception, match="append only"):
            con.execute("UPDATE audit SET reason='tampered'")


def test_premature_execution_remains_approvable(gateway, tokens, db):
    pending = export(gateway, tokens["employee"])
    assert gateway.resume(tokens["employee"], pending["id"])["reason"] == "APPROVAL_NOT_APPROVED"
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    assert gateway.resume(tokens["employee"], pending["id"])["status"] == "succeeded"
    assert count(db, "inbox") == 1


def test_same_key_tamper_invalidates_original_approval(gateway, tokens, db):
    pending = export(gateway, tokens["employee"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    changed = export(gateway, tokens["employee"], ["pub-002"])
    assert changed["reason"] == "IDEMPOTENCY_CONFLICT"
    assert gateway.resume(tokens["employee"], pending["id"])["reason"] == "APPROVAL_INVALIDATED"
    assert count(db, "inbox") == 0


def test_success_audit_failure_rolls_back_business(gateway, tokens, db, monkeypatch):
    import toolguard.gateway as module

    pending = export(gateway, tokens["employee"])
    gateway.decide(tokens["approver"], pending["approval_id"], "approve")
    original = module.audit

    def broken_audit(con, **event):
        if event.get("event") == "execution" and event.get("status") == "succeeded":
            raise RuntimeError("audit write failure")
        return original(con, **event)

    monkeypatch.setattr(module, "audit", broken_audit)
    assert gateway.resume(tokens["employee"], pending["id"])["status"] == "failed"
    assert count(db, "inbox") == 0
    with db.transaction() as con:
        assert con.execute("SELECT status FROM approvals").fetchone()[0] == "approved"
        assert con.execute("SELECT COUNT(*) FROM audit WHERE execution_status='succeeded'").fetchone()[0] == 0


def test_gateway_enforces_task_deadline(gateway, tokens, db):
    first = gateway.invoke(tokens["employee"], request())
    with db.transaction() as con:
        con.execute("UPDATE tasks SET deadline_at=0 WHERE id=?", (first["task_id"],))
    result = gateway.invoke(tokens["employee"], request(key="late", task_id=first["task_id"]))
    assert result["reason"] == "TASK_TIMEOUT"
    assert count(db, "read_receipts") == 1


def test_expired_session_cannot_execute(gateway, tokens, db):
    with db.transaction() as con:
        con.execute("UPDATE sessions SET expires_at=0")
    with pytest.raises(GuardError, match="SESSION_EXPIRED"):
        gateway.invoke(tokens["employee"], request())
    assert count(db, "read_receipts") == 0
