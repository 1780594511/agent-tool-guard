"""Closed tool registry. Only local SQLite effects; no shell, file path or network tool.

This private capability prevents accidental calls in application code. It is not a
Python/OS sandbox: anyone running arbitrary code as the backend user is trusted.
"""

import json
import time
from dataclasses import dataclass

from .db import canonical, digest, uid

_SEAL = object()


@dataclass(frozen=True)
class _Permit:
    seal: object
    user_id: str
    call_id: str
    tool: str
    arguments: dict
    approval_id: str | None


def _issue_permit(user_id, call_id, tool, arguments, approval_id=None):
    return _Permit(_SEAL, user_id, call_id, tool, arguments, approval_id)


def _execute(con, permit: _Permit) -> dict:
    if not isinstance(permit, _Permit) or permit.seal is not _SEAL or not con.in_transaction:
        raise RuntimeError("EXECUTION_PERMIT_REQUIRED")
    args, now = permit.arguments, time.time()
    if permit.tool == "read_document":
        doc = con.execute("SELECT * FROM documents WHERE id=?", (args["document_id"],)).fetchone()
        if not doc:
            raise RuntimeError("RESOURCE_MISSING")
        result = {"document_id": doc["id"], "version": doc["version"], "content_hash": digest(doc["body"])}
        con.execute(
            "INSERT INTO read_receipts VALUES (?,?,?,?,?,?,?)",
            (
                uid("read"),
                permit.user_id,
                permit.call_id,
                doc["id"],
                doc["version"],
                result["content_hash"],
                now,
            ),
        )
        return result
    if permit.tool == "create_ticket":
        ticket_id = uid("ticket")
        con.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?)",
            (ticket_id, permit.user_id, permit.call_id, args["title"], args["body"], now),
        )
        return {"ticket_id": ticket_id, "owner": permit.user_id}
    if permit.tool == "export_report":
        payload = []
        for document_id in args["document_ids"]:
            doc = con.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if not doc:
                raise RuntimeError("RESOURCE_MISSING")
            payload.append(dict(doc))
        inbox_id = uid("export")
        con.execute(
            "INSERT INTO inbox VALUES (?,?,?,?,?,?,?,?)",
            (
                inbox_id,
                permit.user_id,
                permit.call_id,
                args["destination"],
                canonical(args["document_ids"]),
                canonical(payload),
                permit.approval_id,
                now,
            ),
        )
        return {
            "export_id": inbox_id,
            "destination": args["destination"],
            "document_count": len(payload),
            "payload_hash": digest(payload),
        }
    raise RuntimeError("UNKNOWN_EXECUTOR")


def _hydrate_result(con, tool, result):
    result = json.loads(result) if isinstance(result, str) else dict(result)
    if tool == "read_document":
        doc = con.execute("SELECT * FROM documents WHERE id=?", (result["document_id"],)).fetchone()
        if not doc or doc["version"] != result["version"]:
            return {**result, "body": "内容版本已变更，请以新幂等键重新申请读取。"}
        return {**result, "title": doc["title"], "body": doc["body"]}
    return result
