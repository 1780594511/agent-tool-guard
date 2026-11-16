"""Bounded orchestration. The model receives neither credentials nor an execution handle."""

import json
import time

from .auth import GuardError, authenticate
from .db import audit, digest, uid
from .gateway import Gateway
from .models import adapter
from .policy import authorize, current_policy
from .schemas import ToolRequest


def task_view(db, token, task_id):
    with db.transaction() as con:
        principal = authenticate(con, token)
        task = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (task_id, principal.id)).fetchone()
        if not task:
            raise GuardError("TASK_NOT_FOUND", 404)
        version, policy = current_policy(con)
        calls = []
        for call in con.execute("SELECT * FROM calls WHERE task_id=? ORDER BY created_at", (task_id,)):
            visible = dict(call)
            if call["result"]:
                try:
                    authorize(con, principal, policy, call["tool"], json.loads(call["arguments"]))
                except Exception:
                    visible["result"] = None
            calls.append(Gateway._view(con, visible))
        return {
            "id": task["id"],
            "status": task["status"],
            "provider": task["provider"],
            "steps": task["steps"],
            "created_at": task["created_at"],
            "error": task["error"],
            "calls": calls,
            "elapsed_ms": round(((task["ended_at"] or time.time()) - task["created_at"]) * 1000, 3),
            "policy_version": version,
        }


def run_task(db, token, prompt, provider, request_key, *, model=None):
    fingerprint = digest({"prompt": prompt, "provider": provider})
    with db.transaction() as con:
        principal = authenticate(con, token)
        version, policy = current_policy(con)
        existing = con.execute(
            "SELECT * FROM tasks WHERE user_id=? AND request_key=?", (principal.id, request_key)
        ).fetchone()
        if existing:
            if existing["request_hash"] != fingerprint:
                raise GuardError("TASK_IDEMPOTENCY_CONFLICT", 409)
            task_id = existing["id"]
        else:
            task_id, now = uid("task"), time.time()
            con.execute(
                "INSERT INTO tasks (id,user_id,request_key,request_hash,prompt_preview,provider,status,created_at,deadline_at) "
                "VALUES (?,?,?,?,?,?,'running',?,?)",
                (
                    task_id,
                    principal.id,
                    request_key,
                    fingerprint,
                    "任务内容不写入普通日志",
                    provider,
                    now,
                    now + policy.limits.task_timeout_seconds,
                ),
            )
            audit(
                con,
                event="task_started",
                task_id=task_id,
                user_id=principal.id,
                policy_version=version,
                metadata={"prompt_hash": digest(prompt), "prompt_length": len(prompt), "provider": provider},
            )
    if existing:
        return task_view(db, token, task_id)
    gateway, history = Gateway(db), []
    deadline = time.monotonic() + policy.limits.task_timeout_seconds
    terminal, error = "completed", None
    try:
        model = model or adapter(provider)
        with db.transaction() as con:
            audit(
                con,
                event="model_config",
                task_id=task_id,
                user_id=principal.id,
                policy_version=version,
                metadata={
                    "model_id": model.model_id,
                    "max_steps": policy.limits.max_steps,
                    "timeout_seconds": policy.limits.task_timeout_seconds,
                    "model_retries": 0,
                },
            )
        for _ in range(policy.limits.max_steps + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminal, error = "limit_reached", "TASK_TIMEOUT"
                break
            turn = model.next(prompt, history, safety=False, timeout=remaining)
            if not turn.calls:
                terminal = "completed" if history else "no_action"
                break
            for index, proposed in enumerate(turn.calls):
                if len(history) >= policy.limits.max_steps or time.monotonic() >= deadline:
                    terminal, error = "limit_reached", "STEP_OR_TIME_LIMIT"
                    break
                request = ToolRequest(
                    tool=proposed.tool,
                    arguments=proposed.arguments,
                    task_id=task_id,
                    idempotency_key=f"{task_id}:{len(history)}",
                )
                result = gateway.invoke(token, request)
                history.append(
                    {
                        "proposal": proposed,
                        "result": result,
                        "raw_output": turn.raw_output if index == 0 else [],
                    }
                )
                if result["status"] != "succeeded":
                    terminal = {
                        "pending_approval": "waiting_approval",
                        "denied": "blocked",
                        "failed": "failed",
                    }.get(result["status"], "failed")
                    break
            if terminal != "completed":
                break
        else:
            terminal, error = "limit_reached", "STEP_LIMIT"
    except Exception as exc:
        # Provider exceptions can include request headers/body. Do not persist their text.
        terminal = "model_error"
        error = (
            "MODEL_NOT_CONFIGURED"
            if isinstance(exc, ValueError) and str(exc) == "MODEL_NOT_CONFIGURED"
            else "MODEL_OR_GATEWAY_ERROR"
        )
    with db.transaction() as con:
        con.execute(
            "UPDATE tasks SET status=?,error=?,ended_at=? WHERE id=?", (terminal, error, time.time(), task_id)
        )
        audit(
            con,
            event="task_finished",
            task_id=task_id,
            user_id=principal.id,
            policy_version=version,
            reason=error or terminal.upper(),
            status=terminal,
            metadata={"model_output_stored": False},
        )
    return task_view(db, token, task_id)
