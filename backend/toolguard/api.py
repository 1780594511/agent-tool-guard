"""FastAPI transport. Business identities are resolved from HttpOnly sessions only."""

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import run_task, task_view
from .auth import GuardError, authenticate, login, token_hash
from .db import ROOT, Database, audit, canonical, uid, verify_audit
from .gateway import Gateway
from .policy import authorize, current_policy, policy_view, store_policy
from .schemas import (
    AccessUpdate,
    ApprovalAction,
    EvaluationRequest,
    Login,
    PolicyUpdate,
    TaskRequest,
    ToolRequest,
)
from .seed import seed

load_dotenv(ROOT / ".env")
COOKIE = "atg_session"
ALLOWED_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:4173",
    "http://testserver",
}
# Explicit additional local origin for isolated browser tests/custom local ports.
if os.getenv("ATG_UI_ORIGIN", "").startswith("http://127.0.0.1:"):
    ALLOWED_ORIGINS.add(os.environ["ATG_UI_ORIGIN"])


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 65_536:
                return await JSONResponse({"error": "BODY_TOO_LARGE"}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()

        await self.app(scope, replay, send)


def create_app(db_path=None):
    db = Database(db_path or ROOT / os.getenv("ATG_DATABASE", "var/guard.sqlite3"))

    @asynccontextmanager
    async def lifespan(app):
        seed(db)
        # A previous process may have crashed outside a transaction; never replay its task automatically.
        with db.transaction() as con:
            con.execute(
                "UPDATE tasks SET status='interrupted',error='PROCESS_RESTARTED',ended_at=? WHERE status='running'",
                (time.time(),),
            )
            con.execute(
                "UPDATE evaluations SET status='interrupted',error='PROCESS_RESTARTED' WHERE status='running'"
            )
        yield

    app = FastAPI(
        title="Agent Tool Guard",
        version="0.1.0",
        lifespan=lifespan,
        description="Synthetic-only local demo. All protected tools go through /api/gateway/call.",
    )
    app.state.db = db
    app.state.gateway = Gateway(db)
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    def record_http_error(code, request):
        try:
            with db.transaction() as con:
                try:
                    actor = authenticate(con, request.cookies.get(COOKIE)).id
                except GuardError:
                    actor = None
                audit(
                    con,
                    event="http_rejected",
                    user_id=actor,
                    decision="deny",
                    reason=code,
                    status="not_executed",
                )
        except Exception:
            pass  # An unavailable audit store can never turn a denied request into an allowed one.

    @app.exception_handler(GuardError)
    async def guard_error(request, exc):
        record_http_error(exc.code, request)
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        record_http_error("INVALID_REQUEST_ENVELOPE", request)
        return JSONResponse(
            {"error": "INVALID_REQUEST_ENVELOPE", "hint": "身份字段不可由调用参数提供；请检查严格 schema。"},
            status_code=422,
        )

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, exc):
        return JSONResponse({"error": "STORAGE_UNAVAILABLE_NO_EXECUTION"}, status_code=503)

    @app.middleware("http")
    async def harden(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"error": "ORIGIN_FORBIDDEN"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    def session(request: Request):
        token = request.cookies.get(COOKIE)
        csrf = None
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get("x-csrf-token", "")
        with db.transaction() as con:
            principal = authenticate(con, token, csrf)
        return token, principal

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "environment": "synthetic-local"}

    @app.post("/api/auth/login")
    def sign_in(body: Login):
        result = login(db, body.username, body.password)
        response = JSONResponse({"csrf": result["csrf"], "expires_at": result["expires_at"]})
        response.set_cookie(
            COOKIE,
            result["token"],
            httponly=True,
            samesite="strict",
            path="/api",
            secure=os.getenv("ATG_COOKIE_SECURE", "false").lower() == "true",
            max_age=int(result["expires_at"] - time.time()),
        )
        return response

    @app.post("/api/auth/logout")
    def sign_out(auth=Depends(session)):
        with db.transaction() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(auth[0]),))
            audit(con, event="logout", user_id=auth[1].id, reason="SESSION_REVOKED")
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie(COOKIE, path="/api")
        return response

    @app.get("/api/session")
    def identity(auth=Depends(session)):
        token, user = auth
        with db.transaction() as con:
            view = policy_view(con, user)
        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "role": user.role,
                "privileges": user.privileges,
                "approval_scopes": user.approval_scopes,
            },
            "csrf": token_hash("csrf:" + token),
            "access": view,
            "models": {
                "mock": True,
                "openai": bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
                "openai_model": os.getenv("OPENAI_MODEL", "未配置"),
            },
        }

    @app.post("/api/gateway/call")
    def call(body: ToolRequest, auth=Depends(session)):
        return app.state.gateway.invoke(auth[0], body)

    @app.post("/api/calls/{call_id}/execute")
    def execute_approved(call_id: str, auth=Depends(session)):
        return app.state.gateway.resume(auth[0], call_id)

    @app.post("/api/tasks")
    def create_task(body: TaskRequest, auth=Depends(session)):
        return run_task(db, auth[0], body.prompt, body.provider, body.request_key)

    @app.get("/api/tasks")
    def list_tasks(auth=Depends(session)):
        with db.transaction() as con:
            rows = con.execute(
                "SELECT id,status,provider,steps,created_at,error FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                (auth[1].id,),
            )
            return [dict(r) for r in rows]

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str, auth=Depends(session)):
        return task_view(db, auth[0], task_id)

    @app.get("/api/approvals")
    def approvals(auth=Depends(session)):
        user = auth[1]
        with db.transaction() as con:
            rows = []
            for row in con.execute("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 500"):
                scopes = {r["classification"] for r in json.loads(row["resources"])}
                can_review = scopes.issubset(set(user.approval_scopes)) and row["user_id"] != user.id
                if row["user_id"] != user.id and not can_review:
                    continue
                item = dict(row)
                item["arguments"] = json.loads(item["arguments"])
                item["resources"] = json.loads(item["resources"])
                item["can_review"] = can_review
                if item["status"] in {"pending", "approved"} and item["expires_at"] <= time.time():
                    item["status"] = "expired"
                rows.append(item)
            return rows

    @app.post("/api/approvals/{approval_id}/action")
    def decide(approval_id: str, body: ApprovalAction, auth=Depends(session)):
        return app.state.gateway.decide(auth[0], approval_id, body.action)

    @app.get("/api/policy")
    def get_policy(auth=Depends(session)):
        with db.transaction() as con:
            return policy_view(con, auth[1])

    @app.put("/api/policy")
    def update_policy(body: PolicyUpdate, auth=Depends(session)):
        with db.transaction() as con:
            user = authenticate(con, auth[0])
            version = store_policy(con, user, body.expected_version, body.policy)
            audit(
                con,
                event="policy_changed",
                user_id=user.id,
                policy_version=version,
                reason="AUTHORIZED_ADMIN_CHANGE",
                metadata={"previous": body.expected_version},
            )
        return {"version": version}

    @app.get("/api/admin/access")
    def list_access(auth=Depends(session)):
        auth[1].require("manage_access")
        with db.transaction() as con:
            return {
                "users": [dict(r) for r in con.execute("SELECT id,name,role,revision FROM users")],
                "grants": [dict(r) for r in con.execute("SELECT * FROM grants")],
                "documents": [
                    dict(r) for r in con.execute("SELECT id,classification,version FROM documents")
                ],
            }

    @app.post("/api/admin/access")
    def change_access(body: AccessUpdate, auth=Depends(session)):
        with db.transaction() as con:
            user = authenticate(con, auth[0])
            user.require("manage_access")
            if (
                not con.execute("SELECT 1 FROM users WHERE id=?", (body.user_id,)).fetchone()
                or not con.execute("SELECT 1 FROM documents WHERE id=?", (body.document_id,)).fetchone()
            ):
                raise GuardError("SUBJECT_OR_RESOURCE_NOT_FOUND", 404)
            if body.granted:
                con.execute("INSERT OR IGNORE INTO grants VALUES (?,?)", (body.user_id, body.document_id))
            else:
                con.execute(
                    "DELETE FROM grants WHERE user_id=? AND document_id=?", (body.user_id, body.document_id)
                )
            con.execute("UPDATE users SET revision=revision+1 WHERE id=?", (body.user_id,))
            audit(
                con,
                event="access_changed",
                user_id=user.id,
                reason="GRANT" if body.granted else "REVOKE",
                resources=[body.document_id],
                metadata={"subject": body.user_id},
            )
        return {"status": "updated"}

    @app.post("/api/admin/documents/{document_id}/bump-version")
    def bump_version(document_id: str, auth=Depends(session)):
        with db.transaction() as con:
            user = authenticate(con, auth[0])
            user.require("manage_access")
            if not con.execute("UPDATE documents SET version=version+1 WHERE id=?", (document_id,)).rowcount:
                raise GuardError("DOCUMENT_NOT_FOUND", 404)
            audit(
                con,
                event="resource_version_changed",
                user_id=user.id,
                resources=[document_id],
                reason="SYNTHETIC_VERSION_BUMP",
            )
        return {"status": "updated"}

    @app.get("/api/tickets")
    def tickets(auth=Depends(session)):
        with db.transaction() as con:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC", (auth[1].id,)
                )
            ]

    @app.get("/api/inbox")
    def inbox(auth=Depends(session)):
        with db.transaction() as con:
            _, policy = current_policy(con)
            rows = []
            for row in con.execute(
                "SELECT * FROM inbox WHERE user_id=? ORDER BY created_at DESC", (auth[1].id,)
            ):
                try:
                    authorize(
                        con,
                        auth[1],
                        policy,
                        "export_report",
                        {"document_ids": json.loads(row["document_ids"]), "destination": row["destination"]},
                    )
                except GuardError:
                    continue
                item = dict(row)
                item["document_ids"], item["payload"] = (
                    json.loads(row["document_ids"]),
                    json.loads(row["payload"]),
                )
                rows.append(item)
            return rows

    @app.get("/api/audit")
    def audit_log(
        task_id: str | None = None,
        user_id: str | None = None,
        tool: str | None = None,
        decision: str | None = None,
        before: int | None = None,
        auth=Depends(session),
    ):
        conditions, values = [], []
        if "audit_all" not in auth[1].privileges:
            conditions.append("user_id=?")
            values.append(auth[1].id)
        for column, value in (
            ("task_id", task_id),
            ("user_id", user_id),
            ("tool", tool),
            ("decision", decision),
        ):
            if value:
                conditions.append(column + "=?")
                values.append(value)
        if before is not None:
            conditions.append("seq<?")
            values.append(before)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with db.transaction() as con:
            rows = []
            for row in con.execute("SELECT * FROM audit" + where + " ORDER BY seq DESC LIMIT 200", values):
                item = dict(row)
                item["resource_ids"], item["metadata"] = (
                    json.loads(item["resource_ids"]),
                    json.loads(item["metadata"]),
                )
                rows.append(item)
            return rows

    @app.get("/api/audit/verify")
    def integrity(auth=Depends(session)):
        auth[1].require("audit_all")
        with db.transaction() as con:
            return verify_audit(con)

    @app.get("/api/evaluations")
    def evaluations(auth=Depends(session)):
        auth[1].require("evaluate")
        with db.transaction() as con:
            return [
                {
                    **dict(r),
                    "config": json.loads(r["config"]),
                    "result": json.loads(r["result"]) if r["result"] else None,
                }
                for r in con.execute("SELECT * FROM evaluations ORDER BY created_at DESC LIMIT 15")
            ]

    @app.post("/api/evaluations", status_code=202)
    def evaluate(body: EvaluationRequest, background: BackgroundTasks, auth=Depends(session)):
        auth[1].require("evaluate")
        run_id = uid("eval")
        with db.transaction() as con:
            if con.execute("SELECT 1 FROM evaluations WHERE status='running'").fetchone():
                raise GuardError("EVALUATION_ALREADY_RUNNING", 409)
            con.execute(
                "INSERT INTO evaluations VALUES (?,?,?,'running',?,NULL,NULL)",
                (run_id, time.time(), auth[1].id, canonical(body.model_dump())),
            )
            audit(
                con,
                event="evaluation_started",
                user_id=auth[1].id,
                reason="ISOLATED_MOCK_ONLY",
                metadata={"run_id": run_id},
            )
        from .evaluation import background_evaluation

        background.add_task(background_evaluation, db, run_id, body.model_dump())
        return {"id": run_id, "status": "running"}

    assets = ROOT / "frontend/dist/assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api") or not (ROOT / "frontend/dist/index.html").exists():
            return JSONResponse({"error": "NOT_FOUND"}, status_code=404)
        return FileResponse(ROOT / "frontend/dist/index.html")

    return app


app = create_app()
