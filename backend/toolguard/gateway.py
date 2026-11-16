"""Public backend integration: Gateway.invoke(session_token, ToolRequest).

All authorization and execution occur under one BEGIN IMMEDIATE transaction.
Never call the private executor from an Agent; use this class or the HTTP client.
"""

import json
import time

from pydantic import ValidationError

from . import executor
from .auth import GuardError, authenticate
from .db import audit, canonical, digest, uid
from .policy import authorize, binding, current_policy
from .privacy import arguments_preview
from .schemas import TOOL_SCHEMAS, ToolRequest


class Gateway:
    def __init__(self, db):
        self.db = db

    def invoke(self, token: str, request: ToolRequest) -> dict:
        started = time.perf_counter()
        with self.db.transaction() as con:
            principal = authenticate(con, token)
            raw = request.arguments
            request_hash = digest({"tool": request.tool, "arguments": raw})
            version, policy, policy_error = "unknown", None, False
            try:
                version, policy = current_policy(con)
            except Exception:
                policy_error = True
            validation_error = None
            args = raw
            try:
                if request.tool not in TOOL_SCHEMAS:
                    raise GuardError("UNKNOWN_TOOL")
                args = TOOL_SCHEMAS[request.tool].model_validate(raw).model_dump()
                request_hash = digest({"tool": request.tool, "arguments": args})
            except ValidationError:
                validation_error = "INVALID_ARGUMENTS"
            except GuardError as exc:
                validation_error = exc.code

            call = con.execute(
                "SELECT * FROM calls WHERE user_id=? AND idempotency_key=?",
                (principal.id, request.idempotency_key),
            ).fetchone()
            if call:
                if request_hash != call["request_hash"] or (
                    request.task_id and request.task_id != call["task_id"]
                ):
                    if call["approval_id"] and request_hash != call["request_hash"]:
                        con.execute(
                            "UPDATE approvals SET status='invalidated' WHERE id=? AND status IN ('pending','approved')",
                            (call["approval_id"],),
                        )
                    return self._reject_attempt(con, call, "IDEMPOTENCY_CONFLICT", started, args)
                if call["status"] == "succeeded":
                    try:
                        if policy_error:
                            raise GuardError("POLICY_ERROR")
                        authorize(con, principal, policy, request.tool, args)
                    except Exception:
                        return self._reject_attempt(con, call, "REPLAY_ACCESS_DENIED", started, args)
                    audit(
                        con,
                        event="idempotent_replay",
                        user_id=principal.id,
                        task_id=call["task_id"],
                        call_id=call["id"],
                        tool=request.tool,
                        resources=json.loads(call["resources"]),
                        policy_version=version,
                        decision="allow",
                        reason="CACHED_RESULT",
                        status="replayed",
                        approval_id=call["approval_id"],
                    )
                    return self._view(con, call, replayed=True)
                if call["status"] == "denied":
                    audit(
                        con,
                        event="idempotent_replay",
                        user_id=principal.id,
                        task_id=call["task_id"],
                        call_id=call["id"],
                        tool=call["tool"],
                        policy_version=version,
                        decision="deny",
                        reason=call["reason"],
                        approval_id=call["approval_id"],
                        status="not_executed",
                    )
                    return self._view(con, call, replayed=True)
            else:
                task_id = request.task_id or uid("task")
                if request.task_id:
                    task = con.execute(
                        "SELECT * FROM tasks WHERE id=? AND user_id=?", (task_id, principal.id)
                    ).fetchone()
                    if not task:
                        raise GuardError("TASK_NOT_FOUND", 404)
                else:
                    now = time.time()
                    timeout = policy.limits.task_timeout_seconds if policy else 60
                    con.execute(
                        "INSERT INTO tasks (id,user_id,request_key,request_hash,prompt_preview,provider,status,created_at,deadline_at) "
                        "VALUES (?,?,?,?,?,'direct','running',?,?)",
                        (
                            task_id,
                            principal.id,
                            "direct:" + request.idempotency_key,
                            request_hash,
                            "直接工具调用（内容不写入日志）",
                            now,
                            now + timeout,
                        ),
                    )
                call_id = uid("call")
                # Invalid argument payloads are not retained, only their hash and field names.
                stored_args = args if not validation_error else {}
                con.execute(
                    "INSERT INTO calls (id,task_id,user_id,idempotency_key,request_hash,tool,arguments,arguments_preview,resources,"
                    "policy_version,status,reason,created_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'proposed','PROPOSED',?)",
                    (
                        call_id,
                        task_id,
                        principal.id,
                        request.idempotency_key,
                        request_hash,
                        request.tool,
                        canonical(stored_args),
                        canonical(arguments_preview(request.tool, raw)),
                        "[]",
                        version,
                        time.time(),
                    ),
                )
                audit(
                    con,
                    event="proposal",
                    user_id=principal.id,
                    task_id=task_id,
                    call_id=call_id,
                    tool=request.tool,
                    policy_version=version,
                    reason="MODEL_OR_CLIENT_PROPOSAL",
                    metadata=arguments_preview(request.tool, raw),
                )
                call = con.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()

            call_id, task_id = call["id"], call["task_id"]
            resources = []
            approval = None
            try:
                if policy_error:
                    raise GuardError("POLICY_ERROR")
                if validation_error:
                    raise GuardError(validation_error)
                task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
                if call["status"] == "proposed":
                    if task["steps"] >= policy.limits.max_steps:
                        raise GuardError("STEP_LIMIT")
                    if task["deadline_at"] <= time.time():
                        raise GuardError("TASK_TIMEOUT")
                    con.execute("UPDATE tasks SET steps=steps+1 WHERE id=?", (task_id,))
                if call["status"] == "failed" and call["attempts"] >= policy.limits.max_retries + 1:
                    raise GuardError("RETRY_LIMIT")
                if (
                    call["status"] == "failed"
                    and not call["approval_id"]
                    and task["deadline_at"] <= time.time()
                ):
                    raise GuardError("TASK_TIMEOUT")
                resources = authorize(con, principal, policy, request.tool, args)
                con.execute(
                    "UPDATE calls SET resources=?,policy_version=? WHERE id=?",
                    (canonical(resources), version, call_id),
                )

                if request.tool == "export_report":
                    approval_id = request.approval_id or call["approval_id"]
                    if approval_id:
                        approval = con.execute(
                            "SELECT * FROM approvals WHERE id=?", (approval_id,)
                        ).fetchone()
                        self._check_approval(
                            con,
                            approval,
                            principal,
                            call_id,
                            args,
                            resources,
                            version,
                            require_approved=bool(request.approval_id),
                        )
                        if not request.approval_id:
                            return self._pending(con, call_id, approval_id, version, resources, started)
                    else:
                        approval_id = uid("approval")
                        now = time.time()
                        con.execute(
                            "INSERT INTO approvals (id,call_id,user_id,tool,arguments,resources,destination,policy_version,"
                            "subject_revision,fingerprint,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
                            (
                                approval_id,
                                call_id,
                                principal.id,
                                request.tool,
                                canonical(args),
                                canonical(resources),
                                args["destination"],
                                version,
                                principal.revision,
                                binding(principal, request.tool, args, resources, version),
                                now,
                                now + policy.limits.approval_ttl_seconds,
                            ),
                        )
                        return self._pending(con, call_id, approval_id, version, resources, started)
                elif request.approval_id:
                    raise GuardError("APPROVAL_UNEXPECTED")

                # Defense in depth: refreshed session, current policy and permissions immediately before execution.
                fresh = authenticate(con, token)
                current_version, fresh_policy = current_policy(con)
                fresh_resources = authorize(con, fresh, fresh_policy, request.tool, args)
                if fresh_resources != resources or current_version != version:
                    raise GuardError("AUTHORIZATION_CHANGED")
                if time.perf_counter() - started > fresh_policy.limits.task_timeout_seconds:
                    raise GuardError("EXECUTION_TIMEOUT")
                if approval:
                    self._check_approval(
                        con, approval, fresh, call_id, args, resources, version, require_approved=True
                    )
                audit(
                    con,
                    event="execution_recheck",
                    user_id=principal.id,
                    task_id=task_id,
                    call_id=call_id,
                    tool=request.tool,
                    resources=resources,
                    policy_version=version,
                    decision="allow",
                    reason="AUTHORIZED",
                    approval_id=approval["id"] if approval else None,
                    status="ready",
                )
                con.execute("UPDATE calls SET attempts=attempts+1 WHERE id=?", (call_id,))
                con.execute("SAVEPOINT controlled_effect")
                effect_started = time.perf_counter()
                try:
                    permit = executor._issue_permit(
                        principal.id, call_id, request.tool, args, approval["id"] if approval else None
                    )
                    result = executor._execute(con, permit)
                    if time.perf_counter() - started > fresh_policy.limits.task_timeout_seconds:
                        raise RuntimeError("EXECUTION_TIMEOUT")
                    if approval:
                        changed = con.execute(
                            "UPDATE approvals SET status='consumed',consumed_at=? WHERE id=? AND status='approved'",
                            (time.time(), approval["id"]),
                        ).rowcount
                        if changed != 1:
                            raise RuntimeError("APPROVAL_RACE")
                    duration = (time.perf_counter() - started) * 1000
                    con.execute(
                        "UPDATE calls SET status='succeeded',reason='EXECUTED',result=?,duration_ms=?,approval_id=? WHERE id=?",
                        (canonical(result), duration, approval["id"] if approval else None, call_id),
                    )
                    audit(
                        con,
                        event="execution",
                        user_id=principal.id,
                        task_id=task_id,
                        call_id=call_id,
                        tool=request.tool,
                        resources=resources,
                        policy_version=version,
                        decision="allow",
                        reason="EXECUTED",
                        status="succeeded",
                        approval_id=approval["id"] if approval else None,
                        duration_ms=duration,
                        metadata={
                            "result": result,
                            "executor_ms": round((time.perf_counter() - effect_started) * 1000, 3),
                        },
                    )
                    con.execute("RELEASE controlled_effect")
                except Exception:
                    con.execute("ROLLBACK TO controlled_effect")
                    con.execute("RELEASE controlled_effect")
                    duration = (time.perf_counter() - started) * 1000
                    con.execute(
                        "UPDATE calls SET status='failed',reason='EXECUTION_FAILED',duration_ms=? WHERE id=?",
                        (duration, call_id),
                    )
                    audit(
                        con,
                        event="execution",
                        user_id=principal.id,
                        task_id=task_id,
                        call_id=call_id,
                        tool=request.tool,
                        resources=resources,
                        policy_version=version,
                        decision="deny",
                        reason="EXECUTION_FAILED",
                        approval_id=approval["id"] if approval else None,
                        status="rolled_back",
                        duration_ms=duration,
                    )
            except Exception as exc:
                reason = exc.code if isinstance(exc, GuardError) else "AUTHORIZATION_ERROR"
                if reason == "APPROVAL_NOT_APPROVED" and call["status"] == "pending_approval":
                    # A premature execution attempt must not destroy a still-reviewable request.
                    return self._reject_attempt(con, call, reason, started, args)
                if request.approval_id:
                    supplied = con.execute(
                        "SELECT * FROM approvals WHERE id=? AND user_id=?",
                        (request.approval_id, principal.id),
                    ).fetchone()
                    if supplied and supplied["arguments"] != canonical(args):
                        con.execute(
                            "UPDATE approvals SET status='invalidated' WHERE id=? AND status IN ('pending','approved')",
                            (supplied["id"],),
                        )
                if call["approval_id"] and reason in {
                    "RESOURCE_FORBIDDEN",
                    "TOOL_FORBIDDEN",
                    "DESTINATION_FORBIDDEN",
                    "POLICY_ERROR",
                }:
                    con.execute(
                        "UPDATE approvals SET status='invalidated' WHERE id=? AND status IN ('pending','approved')",
                        (call["approval_id"],),
                    )
                duration = (time.perf_counter() - started) * 1000
                con.execute(
                    "UPDATE calls SET status='denied',reason=?,duration_ms=? WHERE id=?",
                    (reason, duration, call_id),
                )
                audit(
                    con,
                    event="decision",
                    user_id=principal.id,
                    task_id=task_id,
                    call_id=call_id,
                    tool=request.tool,
                    resources=resources,
                    policy_version=version,
                    decision="deny",
                    reason=reason,
                    approval_id=request.approval_id or call["approval_id"],
                    status="not_executed",
                    duration_ms=duration,
                )
            self._sync_task(con, task_id)
            return self._view(con, con.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone())

    def _pending(self, con, call_id, approval_id, version, resources, started):
        duration = (time.perf_counter() - started) * 1000
        con.execute(
            "UPDATE calls SET status='pending_approval',reason='APPROVAL_REQUIRED',approval_id=?,duration_ms=? WHERE id=?",
            (approval_id, duration, call_id),
        )
        call = con.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
        audit(
            con,
            event="decision",
            user_id=call["user_id"],
            task_id=call["task_id"],
            call_id=call_id,
            tool=call["tool"],
            resources=resources,
            policy_version=version,
            decision="pending",
            reason="APPROVAL_REQUIRED",
            approval_id=approval_id,
            status="not_executed",
            duration_ms=duration,
        )
        self._sync_task(con, call["task_id"])
        return self._view(con, call)

    def _reject_attempt(self, con, call, reason, started, args):
        audit(
            con,
            event="rejected_attempt",
            user_id=call["user_id"],
            task_id=call["task_id"],
            call_id=call["id"],
            tool=call["tool"],
            policy_version=call["policy_version"],
            decision="deny",
            reason=reason,
            status="not_executed",
            duration_ms=(time.perf_counter() - started) * 1000,
            metadata=arguments_preview(call["tool"], args),
        )
        return {
            "id": call["id"],
            "task_id": call["task_id"],
            "status": "denied",
            "reason": reason,
            "result": None,
            "tool": call["tool"],
            "replayed": False,
        }

    @staticmethod
    def _check_approval(con, approval, principal, call_id, args, resources, version, *, require_approved):
        if not approval or approval["user_id"] != principal.id:
            raise GuardError("APPROVAL_NOT_FOUND")
        if approval["status"] in {"consumed", "revoked", "rejected", "expired", "invalidated"}:
            raise GuardError("APPROVAL_" + approval["status"].upper())
        if approval["expires_at"] <= time.time():
            con.execute("UPDATE approvals SET status='expired' WHERE id=?", (approval["id"],))
            raise GuardError("APPROVAL_EXPIRED")
        expected = binding(principal, "export_report", args, resources, version)
        if approval["call_id"] != call_id or approval["fingerprint"] != expected:
            con.execute("UPDATE approvals SET status='invalidated' WHERE id=?", (approval["id"],))
            raise GuardError("APPROVAL_BINDING_MISMATCH")
        if require_approved:
            if approval["status"] != "approved":
                raise GuardError("APPROVAL_NOT_APPROVED")
            reviewer = con.execute(
                "SELECT * FROM users WHERE id=? AND active=1", (approval["approver_id"],)
            ).fetchone()
            if not reviewer or reviewer["id"] == principal.id:
                raise GuardError("APPROVER_INVALID")
            if not {r["classification"] for r in resources}.issubset(
                set(json.loads(reviewer["approval_scopes"]))
            ):
                raise GuardError("APPROVER_PERMISSION_REVOKED")

    @staticmethod
    def _sync_task(con, task_id):
        states = [r[0] for r in con.execute("SELECT status FROM calls WHERE task_id=?", (task_id,))]
        status = (
            "waiting_approval"
            if "pending_approval" in states
            else ("blocked" if "denied" in states else ("failed" if "failed" in states else "completed"))
        )
        con.execute("UPDATE tasks SET status=?,ended_at=? WHERE id=?", (status, time.time(), task_id))

    @staticmethod
    def _view(con, call, replayed=False):
        result = executor._hydrate_result(con, call["tool"], call["result"]) if call["result"] else None
        return {
            "id": call["id"],
            "task_id": call["task_id"],
            "tool": call["tool"],
            "status": call["status"],
            "reason": call["reason"],
            "approval_id": call["approval_id"],
            "policy_version": call["policy_version"],
            "arguments": json.loads(call["arguments_preview"]),
            "resources": json.loads(call["resources"]),
            "duration_ms": round(call["duration_ms"], 3),
            "result": result,
            "replayed": replayed,
        }

    def resume(self, token, call_id):
        with self.db.transaction() as con:
            principal = authenticate(con, token)
            call = con.execute(
                "SELECT * FROM calls WHERE id=? AND user_id=?", (call_id, principal.id)
            ).fetchone()
            if not call:
                raise GuardError("CALL_NOT_FOUND", 404)
            request = ToolRequest(
                tool=call["tool"],
                arguments=json.loads(call["arguments"]),
                idempotency_key=call["idempotency_key"],
                task_id=call["task_id"],
                approval_id=call["approval_id"],
            )
        return self.invoke(token, request)

    def decide(self, token, approval_id, action):
        error = None
        with self.db.transaction() as con:
            principal = authenticate(con, token)
            approval = con.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not approval:
                raise GuardError("APPROVAL_NOT_FOUND", 404)
            resources = json.loads(approval["resources"])
            required_scopes = {r["classification"] for r in resources}
            # Revocation by the requester is also allowed; approval/rejection never is.
            owner_revoke = action == "revoke" and approval["user_id"] == principal.id
            if not owner_revoke and not required_scopes.issubset(set(principal.approval_scopes)):
                raise GuardError("APPROVAL_PERMISSION_REQUIRED")
            if action != "revoke" and approval["user_id"] == principal.id:
                raise GuardError("SELF_APPROVAL_FORBIDDEN")
            if approval["status"] not in {"pending", "approved"}:
                raise GuardError("APPROVAL_NOT_ACTIONABLE", 409)
            if action in {"approve", "reject"} and approval["status"] != "pending":
                raise GuardError("APPROVAL_ALREADY_DECIDED", 409)
            if approval["expires_at"] <= time.time():
                con.execute("UPDATE approvals SET status='expired' WHERE id=?", (approval_id,))
                error = GuardError("APPROVAL_EXPIRED", 409)
            elif action == "approve":
                try:
                    from .auth import Principal

                    row = con.execute(
                        "SELECT * FROM users WHERE id=? AND active=1", (approval["user_id"],)
                    ).fetchone()
                    if not row:
                        raise GuardError("REQUESTER_INACTIVE")
                    owner = Principal.from_row(row)
                    version, policy = current_policy(con)
                    args = json.loads(approval["arguments"])
                    current_resources = authorize(con, owner, policy, approval["tool"], args)
                    self._check_approval(
                        con,
                        approval,
                        owner,
                        approval["call_id"],
                        args,
                        current_resources,
                        version,
                        require_approved=False,
                    )
                except Exception as exc:
                    con.execute("UPDATE approvals SET status='invalidated' WHERE id=?", (approval_id,))
                    error = GuardError(exc.code if isinstance(exc, GuardError) else "POLICY_ERROR", 409)
            status = {"approve": "approved", "reject": "rejected", "revoke": "revoked"}[action]
            if not error:
                reviewer_id = approval["approver_id"] if action == "revoke" else principal.id
                con.execute(
                    "UPDATE approvals SET status=?,approver_id=?,decided_at=? WHERE id=?",
                    (status, reviewer_id, time.time(), approval_id),
                )
            effective = con.execute("SELECT status FROM approvals WHERE id=?", (approval_id,)).fetchone()[0]
            if effective in {"rejected", "revoked", "expired", "invalidated"}:
                con.execute(
                    "UPDATE calls SET status='denied',reason=? WHERE id=? AND status!='succeeded'",
                    ("APPROVAL_" + effective.upper(), approval["call_id"]),
                )
                task_id = con.execute(
                    "SELECT task_id FROM calls WHERE id=?", (approval["call_id"],)
                ).fetchone()[0]
                self._sync_task(con, task_id)
            audit(
                con,
                event="approval_action",
                user_id=principal.id,
                call_id=approval["call_id"],
                task_id=con.execute(
                    "SELECT task_id FROM calls WHERE id=?", (approval["call_id"],)
                ).fetchone()[0],
                tool=approval["tool"],
                resources=resources,
                policy_version=approval["policy_version"],
                approval_id=approval_id,
                decision="deny" if error else "allow",
                reason=error.code if error else status.upper(),
                status="not_executed",
                metadata={"requester": approval["user_id"]},
            )
        if error:
            raise error
        return {"id": approval_id, "status": status}
