"""Deterministic ABAC/RBAC decisions. No model call is involved here."""

import json

from .auth import GuardError
from .db import canonical, digest
from .schemas import Policy


def current_policy(con) -> tuple[str, Policy]:
    row = con.execute("SELECT version,body FROM policies WHERE active=1").fetchone()
    if not row:
        raise GuardError("POLICY_UNAVAILABLE", 503)
    return row["version"], Policy.model_validate(json.loads(row["body"]))


def permitted_document(con, principal, policy, document_id):
    row = con.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    rule = policy.roles.get(principal.role)
    if not row or not rule or row["classification"] not in rule.classifications:
        raise GuardError("RESOURCE_FORBIDDEN")
    if row["classification"] != "public":
        grant = con.execute(
            "SELECT 1 FROM grants WHERE user_id=? AND document_id=?", (principal.id, document_id)
        ).fetchone()
        if not grant:
            raise GuardError("RESOURCE_FORBIDDEN")
    return row


def authorize(con, principal, policy, tool, args) -> list[dict]:
    rule = policy.roles.get(principal.role)
    if not rule or tool not in rule.tools:
        raise GuardError("TOOL_FORBIDDEN")
    ids = [args["document_id"]] if tool == "read_document" else args.get("document_ids", [])
    resources = []
    for resource_id in ids:
        row = permitted_document(con, principal, policy, resource_id)
        resources.append(
            {"id": row["id"], "version": row["version"], "classification": row["classification"]}
        )
    if tool == "export_report" and args["destination"] not in policy.destinations:
        raise GuardError("DESTINATION_FORBIDDEN")
    return resources


def binding(principal, tool, args, resources, version):
    return digest(
        {
            "user_id": principal.id,
            "subject_revision": principal.revision,
            "tool": tool,
            "arguments": args,
            "resources": resources,
            "destination": args.get("destination"),
            "policy_version": version,
        }
    )


def policy_view(con, principal):
    version, policy = current_policy(con)
    docs = []
    for row in con.execute("SELECT id FROM documents ORDER BY id"):
        try:
            if "read_document" not in policy.roles[principal.role].tools:
                continue
            doc = permitted_document(con, principal, policy, row["id"])
            docs.append({key: doc[key] for key in ("id", "title", "classification", "version")})
        except GuardError:
            continue
    return {
        "version": version,
        "policy": policy.model_dump(),
        "documents": docs,
        "rule": policy.roles[principal.role].model_dump(),
        "boundary": "限制策略禁止的操作；不检测或防御所有提示注入。审批不赋予资源读取权。",
    }


def store_policy(con, principal, expected_version, policy):
    principal.require("manage_policy")
    current, _ = current_policy(con)
    if current != expected_version:
        raise GuardError("POLICY_VERSION_CONFLICT", 409)
    body = policy.model_dump()
    version = "p_" + digest({"body": body, "previous": current})[:16]
    con.execute("UPDATE policies SET active=0 WHERE active=1")
    import time

    con.execute(
        "INSERT INTO policies VALUES (?,?,?,?,1)", (version, canonical(body), time.time(), principal.id)
    )
    return version
