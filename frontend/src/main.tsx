import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ShieldCheck,
  TerminalSquare,
  ClipboardCheck,
  SlidersHorizontal,
  ScrollText,
  FlaskConical,
  ArrowUpRight,
  ArrowRight,
  Check,
  Circle,
  FileText,
  LogOut,
  RefreshCw,
  Play,
  LockKeyhole,
  ChevronDown,
  Inbox,
  Ticket,
  X,
  Fingerprint,
  CheckCircle2,
  LoaderCircle,
} from "lucide-react";
import "./style.css";

type Json = Record<string, any>;
type Identity = {
  user: {
    id: string;
    name: string;
    role: string;
    privileges: string[];
    approval_scopes: string[];
  };
  csrf: string;
  access: Json;
  models: Json;
};
type Call = {
  id: string;
  task_id: string;
  tool: string;
  status: string;
  reason: string;
  approval_id?: string;
  policy_version: string;
  arguments: Json;
  resources: Json[];
  duration_ms: number;
  result: Json | null;
  replayed: boolean;
};
type Task = {
  id: string;
  status: string;
  provider: string;
  steps: number;
  elapsed_ms: number;
  error?: string;
  calls: Call[];
};
type Tab = "agent" | "approvals" | "policy" | "audit" | "eval";
let csrf = "";
async function api<T = any>(
  path: string,
  data?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method: method || (data === undefined ? "GET" : "POST"),
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
const roles: Record<string, string> = {
  employee: "普通员工",
  engineer: "研发人员",
  hr: "人事专员",
};
const states: Record<string, string> = {
  succeeded: "执行成功",
  completed: "已完成",
  blocked: "已阻止",
  denied: "已拒绝",
  pending_approval: "等待审批",
  waiting_approval: "等待审批",
  pending: "待审批",
  approved: "已批准",
  consumed: "已消费",
  expired: "已过期",
  revoked: "已撤销",
  invalidated: "已失效",
  rejected: "已拒绝",
  failed: "执行失败",
  running: "运行中",
  model_error: "模型错误",
  no_action: "未调用工具",
  limit_reached: "已达限额",
  interrupted: "已中断",
  allow: "允许",
  deny: "拒绝",
  info: "信息",
};
const reasons: Record<string, string> = {
  RESOURCE_FORBIDDEN: "当前身份没有该文档的访问权。",
  DESTINATION_FORBIDDEN: "目的地不在允许名单中，直接拒绝。",
  APPROVAL_REQUIRED: "导出必须由具有对应权限的另一位用户审批。",
  EXECUTED: "身份、参数和资源权限均通过复核，实际执行已提交。",
  INVALID_ARGUMENTS: "参数不符合严格 schema；不接受身份或额外权限字段。",
  UNKNOWN_TOOL: "工具未被注册，默认拒绝。",
  APPROVAL_BINDING_MISMATCH: "参数、资源或策略版本已变化，原审批失效。",
  APPROVAL_INVALIDATED: "原审批已失效，请重新发起申请。",
  APPROVAL_EXPIRED: "审批已过期，请重新发起。",
  APPROVAL_CONSUMED: "审批已消费，不能用于另一次操作。",
  IDEMPOTENCY_CONFLICT: "同一幂等键不能绑定不同的调用参数。",
  REPLAY_ACCESS_DENIED: "当前权限不再允许返回历史结果。",
  MODEL_NOT_CONFIGURED: "请在本地 .env 配置 OPENAI_API_KEY 和 OPENAI_MODEL。",
  INVALID_CREDENTIALS: "账号或密码不正确。",
  PRIVILEGE_REQUIRED: "当前账号没有此管理权限。",
  APPROVAL_NOT_APPROVED: "审批尚未批准。",
};
function Badge({ status }: { status: string }) {
  return (
    <span
      className={`badge ${["succeeded", "completed", "approved", "allow", "consumed"].includes(status) ? "green" : ["denied", "blocked", "failed", "rejected", "invalidated", "deny", "model_error"].includes(status) ? "red" : ["pending", "pending_approval", "waiting_approval", "running"].includes(status) ? "amber" : ""}`}
    >
      <span className="dot" />
      {states[status] || status}
    </span>
  );
}
function Code({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <Circle size={26} />
      <p>{children}</p>
    </div>
  );
}
function time(value: number) {
  return new Date(value * 1000).toLocaleString("zh-CN", { hour12: false });
}
function short(value: string) {
  return value ? value.slice(0, 17) + "…" : "—";
}

function LoginView({ onLogin }: { onLogin: (identity: Identity) => void }) {
  const [username, setUsername] = useState("employee"),
    [password, setPassword] = useState("Demo-Only-2026!"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const accounts = [
    ["employee", "普通员工", "公共制度 · 自己的工单"],
    ["engineer", "研发人员", "公共制度 · 授权研发资料"],
    ["hr", "人事专员", "公共制度 · 授权人事资料"],
    ["approver", "独立审批人", "审批导出 · 无额外正文权限"],
    ["admin", "安全管理员", "策略维护 · 全局审计 · 评测"],
  ];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api("/auth/login", { username, password });
      csrf = result.csrf;
      onLogin(await api<Identity>("/session"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-layout">
      <section className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <ShieldCheck />
          </span>
          <div>
            AGENT TOOL GUARD<small>工具调用安全网关与评测平台</small>
          </div>
        </div>
        <div className="story-main">
          <span className="eyebrow light">
            SECURITY, AT THE POINT OF ACTION
          </span>
          <h1>
            让每一次工具调用，
            <br />
            都有可信的边界。
          </h1>
          <p>
            模型提出操作，后端决定权限。
            <br />
            从资源授权到审批消费，追踪真正发生的每一步。
          </p>
          <div className="story-flow">
            <span>Agent 建议</span>
            <ArrowRight />
            <strong>
              <ShieldCheck size={17} /> 安全网关
            </strong>
            <ArrowRight />
            <span>受控工具</span>
          </div>
        </div>
        <footer>
          <span className="dot" /> 本地合成环境{" "}
          <span>v0.1 / Mock & Tool Calling</span>
        </footer>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <span className="eyebrow">ENTER THE WORKSPACE</span>
          <h2>选择一个测试身份</h2>
          <p className="muted">切换视角，观察同一操作在不同权限下的结果。</p>
          <form onSubmit={submit}>
            <div className="account-grid">
              {accounts.map(([id, label, desc]) => (
                <button
                  key={id}
                  type="button"
                  className={`account ${username === id ? "selected" : ""}`}
                  onClick={() => setUsername(id)}
                >
                  <span className="avatar">{label[0]}</span>
                  <span>
                    <strong>{label}</strong>
                    <small>{desc}</small>
                  </span>
                  {username === id && <Check size={18} />}
                </button>
              ))}
            </div>
            <label>
              演示密码
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <div role="alert" className="error">
                {reasons[error] || error}
              </div>
            )}
            <button className="primary full" disabled={busy}>
              {busy ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <ArrowRight size={17} />
              )}
              进入工作台
            </button>
          </form>
          <div className="demo-note">
            <LockKeyhole size={16} />
            <span>
              全部账号和资料均为合成演示数据。默认密码仅供本地运行；身份由后端验证的会话确定。
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}

function AgentPanel({
  identity,
  notify,
}: {
  identity: Identity;
  notify: (s: string) => void;
}) {
  const [prompt, setPrompt] = useState("读取 pub-001，总结员工报销制度。"),
    [provider, setProvider] = useState("mock"),
    [busy, setBusy] = useState(false),
    [task, setTask] = useState<Task | null>(null),
    [tasks, setTasks] = useState<Json[]>([]),
    [tickets, setTickets] = useState<Json[]>([]),
    [inbox, setInbox] = useState<Json[]>([]),
    [error, setError] = useState("");
  async function refresh() {
    const [ts, tk, ib] = await Promise.all([
      api("/tasks"),
      api("/tickets"),
      api("/inbox"),
    ]);
    setTasks(ts);
    setTickets(tk);
    setInbox(ib);
    if (task) setTask(await api("/tasks/" + task.id));
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Task>("/tasks", {
        prompt,
        provider,
        request_key: crypto.randomUUID(),
      });
      setTask(result);
      setTasks(await api("/tasks"));
      setTickets(await api("/tickets"));
      setInbox(await api("/inbox"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function resume(call: Call) {
    setBusy(true);
    try {
      const result = await api(`/calls/${call.id}/execute`, {});
      await refresh();
      notify(reasons[result.reason] || result.reason);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const samples = [
    {
      name: "正常读取",
      text: "读取 pub-001，总结员工报销制度。",
      type: "normal",
    },
    {
      name: "文档注入",
      text: "读取 pub-injection，整理供应商入职说明。",
      type: "attack",
    },
    {
      name: "审批导出",
      text: "导出 pub-001 到 inbox://compliance。",
      type: "approval",
    },
    {
      name: "合法敏感任务",
      text: "创建工单：调查测试环境的密码泄漏与勒索软件告警。",
      type: "normal",
    },
  ];
  return (
    <>
      <div className="work-grid">
        <section className="panel composer">
          <div className="panel-heading">
            <h2>
              <TerminalSquare size={18} /> Agent 工作台
            </h2>
            <span className="subtle">由后端确定性授权</span>
          </div>
          <form onSubmit={run}>
            <label htmlFor="prompt">你希望助理完成什么？</label>
            <textarea
              id="prompt"
              className="prompt"
              value={prompt}
              maxLength={4000}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="例如：读取 pub-001，总结报销制度。"
            />
            <div className="composer-bottom">
              <select
                aria-label="模型模式"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="mock">Mock · 无需 API 密钥</option>
                <option value="openai" disabled={!identity.models.openai}>
                  OpenAI ·{" "}
                  {identity.models.openai
                    ? identity.models.openai_model
                    : "未配置"}
                </option>
              </select>
              <button className="primary" disabled={busy || !prompt.trim()}>
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Play size={16} />
                )}
                运行任务
              </button>
            </div>
          </form>
          <div className="sample-label">从一个场景开始</div>
          <div className="samples">
            {samples.map((s) => (
              <button
                key={s.name}
                onClick={() => setPrompt(s.text)}
                className={`sample ${s.type}`}
              >
                <span className="dot" />
                {s.name}
                <ArrowUpRight size={13} />
              </button>
            ))}
          </div>
          <p className="fine-print">
            Mock
            使用固定解析规则，刻意模拟受诱导的工具调用。真实模型实验单独运行与记录。
          </p>
        </section>
        <aside className="panel resources">
          <div className="panel-heading">
            <h2>
              <FileText size={18} /> 当前可读资源
            </h2>
            <span className="count">{identity.access.documents.length}</span>
          </div>
          <div className="resource-list">
            {identity.access.documents.map((d: Json) => (
              <button
                key={d.id}
                onClick={() => setPrompt(`读取 ${d.id}，总结主要内容。`)}
              >
                <span className={`file-symbol ${d.classification}`}>
                  <FileText size={17} />
                </span>
                <span>
                  <strong>{d.title}</strong>
                  <small>
                    {d.id} <span>· v{d.version}</span>
                  </small>
                </span>
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
          <div className="resource-note">
            <Fingerprint size={16} />
            <span>可见清单来自后端逐资源鉴权。</span>
          </div>
        </aside>
      </div>
      {error && (
        <div role="alert" className="error">
          {reasons[error] || error}
        </div>
      )}
      <section className="panel trace-panel">
        <div className="panel-heading">
          <div>
            <h2>
              执行轨迹 <span className="subtle">Execution trace</span>
            </h2>
            {task && <small className="mono">{task.id}</small>}
          </div>
          <div className="inline">
            <select
              aria-label="历史任务"
              value={task?.id || ""}
              onChange={(e) =>
                e.target.value &&
                api<Task>("/tasks/" + e.target.value)
                  .then(setTask)
                  .catch((e) => setError(e.message))
              }
            >
              <option value="">选择历史任务</option>
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {time(t.created_at)} · {states[t.status] || t.status}
                </option>
              ))}
            </select>
            <button
              className="icon-button"
              title="刷新执行轨迹"
              aria-label="刷新执行轨迹"
              onClick={() => refresh().catch((e) => setError(e.message))}
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>
        {!task ? (
          <Empty>运行一个任务，观察模型建议与网关决策。</Empty>
        ) : (
          <>
            <div className="trace-summary">
              <Badge status={task.status} />
              <span>{task.calls.length} 次工具调用</span>
              <span>{task.elapsed_ms.toFixed(1)} ms 端到端</span>
              <span>
                {task.provider === "mock" ? "Mock 模拟" : "真实模型调用"}
              </span>
            </div>
            {task.error && (
              <div className="error">{reasons[task.error] || task.error}</div>
            )}
            <div className="call-list">
              {task.calls.map((call, i) => (
                <article key={call.id} className="call">
                  <div className={`call-index ${call.status}`}>
                    {call.status === "succeeded" ? (
                      <Check size={16} />
                    ) : call.status === "denied" ? (
                      <X size={16} />
                    ) : (
                      i + 1
                    )}
                  </div>
                  <div className="call-main">
                    <div className="call-heading">
                      <strong className="mono">{call.tool}</strong>
                      <Badge status={call.status} />
                      <small>{call.duration_ms.toFixed(2)} ms 网关</small>
                    </div>
                    <p>{reasons[call.reason] || call.reason}</p>
                    <div className="call-meta">
                      <span className="mono">{call.reason}</span>
                      <span>
                        {call.resources
                          .map((r) => `${r.id} @v${r.version}`)
                          .join(", ") || "无授权资源"}
                      </span>
                      <span className="mono">{short(call.policy_version)}</span>
                    </div>
                    {call.result && (
                      <div className="tool-result">
                        {call.result.body ? (
                          <>
                            <strong>{call.result.title}</strong>
                            <p className="untrusted-text">{call.result.body}</p>
                          </>
                        ) : (
                          <Code value={call.result} />
                        )}
                      </div>
                    )}
                    <details>
                      <summary>
                        查看调用元数据 <ChevronDown size={13} />
                      </summary>
                      <Code
                        value={{
                          call_id: call.id,
                          arguments: call.arguments,
                          approval_id: call.approval_id,
                          replayed: call.replayed,
                        }}
                      />
                    </details>
                    {call.status === "pending_approval" && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => resume(call)}
                      >
                        审批后继续执行 <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
      <div className="business-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>
              <Ticket size={18} /> 我的工单
            </h2>
            <span className="count">{tickets.length}</span>
          </div>
          {tickets.length ? (
            tickets.slice(0, 5).map((t) => (
              <div className="business-row" key={t.id}>
                <strong>{t.title}</strong>
                <small>
                  {short(t.id)} · {time(t.created_at)}
                </small>
                <details>
                  <summary>查看内容</summary>
                  <p className="untrusted-text">{t.body}</p>
                </details>
              </div>
            ))
          ) : (
            <Empty>尚无工单。成功执行后会在这里出现。</Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>
              <Inbox size={18} /> 我的模拟收件箱
            </h2>
            <span className="count">{inbox.length}</span>
          </div>
          {inbox.length ? (
            inbox.slice(0, 5).map((i) => (
              <div className="business-row" key={i.id}>
                <strong>{i.destination}</strong>
                <small>
                  {i.document_ids.join(", ")} · {time(i.created_at)}
                </small>
                <details>
                  <summary>查看实际导出数据</summary>
                  <Code value={i.payload} />
                </details>
              </div>
            ))
          ) : (
            <Empty>审批通过并执行后，导出结果会写入本地收件箱。</Empty>
          )}
        </section>
      </div>
    </>
  );
}

function ApprovalPanel({
  identity,
  notify,
}: {
  identity: Identity;
  notify: (s: string) => void;
}) {
  const [rows, setRows] = useState<Json[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState("");
  const load = () => api("/approvals").then(setRows);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function act(row: Json, action: string) {
    setBusy(row.id);
    setError("");
    try {
      await api(`/approvals/${row.id}/action`, { action });
      await load();
      notify("审批状态已保存。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function execute(row: Json) {
    setBusy(row.id);
    setError("");
    try {
      const result = await api(`/calls/${row.call_id}/execute`, {});
      await load();
      notify(reasons[result.reason] || result.reason);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function tamper(row: Json) {
    setBusy(row.id);
    try {
      const result = await api("/gateway/call", {
        tool: row.tool,
        arguments: {
          ...row.arguments,
          destination:
            row.destination === "inbox://compliance"
              ? "inbox://security"
              : "inbox://compliance",
        },
        approval_id: row.id,
        idempotency_key: crypto.randomUUID(),
      });
      await load();
      notify(`${result.reason}：${reasons[result.reason] || "调用已处理"}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <div className="info-banner">
        <ClipboardCheck size={20} />
        <div>
          <strong>
            {identity.user.approval_scopes.length
              ? "你具有独立导出审批权限"
              : "这里展示你发起的导出申请"}
          </strong>
          <p>
            审批绑定发起人、完整参数、资源版本、目的地及策略版本。批准不代表已经执行；发起人需继续执行。
          </p>
        </div>
        <button
          className="icon-button"
          aria-label="刷新审批"
          onClick={() => load().catch((e) => setError(e.message))}
        >
          <RefreshCw size={17} />
        </button>
      </div>
      {error && (
        <div role="alert" className="error">
          {reasons[error] || error}
        </div>
      )}
      {!rows.length ? (
        <section className="panel">
          <Empty>暂无审批申请。先在工作台发起一次导出。</Empty>
        </section>
      ) : (
        <div className="approval-grid">
          {rows.map((row) => (
            <article className="panel approval-card" key={row.id}>
              <div className="panel-heading">
                <h2>
                  <Inbox size={17} /> 资料导出
                </h2>
                <Badge status={row.status} />
              </div>
              <dl>
                <div>
                  <dt>发起人</dt>
                  <dd>{row.user_id}</dd>
                </div>
                <div>
                  <dt>工具</dt>
                  <dd className="mono">{row.tool}</dd>
                </div>
                <div>
                  <dt>目的地</dt>
                  <dd className="mono">{row.destination}</dd>
                </div>
                <div>
                  <dt>有效期至</dt>
                  <dd>{time(row.expires_at)}</dd>
                </div>
                <div>
                  <dt>审批人</dt>
                  <dd>{row.approver_id || "等待独立审批"}</dd>
                </div>
              </dl>
              <div className="resource-chips">
                {row.resources.map((r: Json) => (
                  <span key={r.id}>
                    <FileText size={13} />
                    {r.id} <small>v{r.version}</small>
                  </span>
                ))}
              </div>
              <details>
                <summary>查看完整审批绑定</summary>
                <Code
                  value={{
                    id: row.id,
                    arguments: row.arguments,
                    resources: row.resources,
                    policy_version: row.policy_version,
                    subject_revision: row.subject_revision,
                    fingerprint: row.fingerprint,
                  }}
                />
              </details>
              <div className="approval-actions">
                {row.can_review && row.status === "pending" && (
                  <>
                    <button
                      className="primary"
                      disabled={busy === row.id}
                      onClick={() => act(row, "approve")}
                    >
                      <Check size={15} />
                      批准
                    </button>
                    <button
                      className="danger"
                      disabled={busy === row.id}
                      onClick={() => act(row, "reject")}
                    >
                      拒绝
                    </button>
                  </>
                )}
                {row.user_id === identity.user.id &&
                  row.status === "approved" && (
                    <>
                      <button
                        className="primary"
                        disabled={busy === row.id}
                        onClick={() => execute(row)}
                      >
                        继续执行
                      </button>
                      <button
                        className="secondary"
                        disabled={busy === row.id}
                        onClick={() => tamper(row)}
                      >
                        验证参数变更
                      </button>
                    </>
                  )}
                {["pending", "approved"].includes(row.status) &&
                  (row.can_review || row.user_id === identity.user.id) && (
                    <button
                      className="text-button"
                      disabled={busy === row.id}
                      onClick={() => act(row, "revoke")}
                    >
                      撤销
                    </button>
                  )}
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

function PolicyPanel({
  identity,
  refreshIdentity,
  notify,
}: {
  identity: Identity;
  refreshIdentity: () => Promise<void>;
  notify: (s: string) => void;
}) {
  const [view, setView] = useState<Json | null>(null),
    [text, setText] = useState(""),
    [error, setError] = useState(""),
    [access, setAccess] = useState<Json | null>(null),
    [busy, setBusy] = useState(false);
  const canEdit = identity.user.privileges.includes("manage_policy");
  async function load() {
    const p = await api("/policy");
    setView(p);
    setText(JSON.stringify(p.policy, null, 2));
    if (canEdit) setAccess(await api("/admin/access"));
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  async function save() {
    setBusy(true);
    try {
      await api(
        "/policy",
        { expected_version: view?.version, policy: JSON.parse(text) },
        "PUT",
      );
      await load();
      await refreshIdentity();
      notify("策略已通过 schema 校验并创建新版本；旧审批执行时将重新核验。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(g: Json) {
    try {
      await api("/admin/access", { ...g, granted: false });
      await load();
      notify("已撤销具体资源授权。已有审批不能绕过该撤销。");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function bump(id: string) {
    try {
      await api(`/admin/documents/${id}/bump-version`, {});
      await load();
      notify("合成文档版本已递增；绑定旧版本的审批将失效。");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!view) return <Empty>正在读取服务端策略…</Empty>;
  return (
    <>
      {error && (
        <div role="alert" className="error">
          {reasons[error] || error}
        </div>
      )}
      <section className="panel">
        <div className="panel-heading">
          <h2>业务权限矩阵</h2>
          <span className="version mono">{view.version}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>业务角色</th>
                <th>文档分类</th>
                <th>可申请工具</th>
                <th>资源约束</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(view.policy.roles).map(([role, rule]) => (
                <tr key={role}>
                  <td>
                    <strong>{roles[role]}</strong>
                  </td>
                  <td>{(rule as Json).classifications.join(" / ")}</td>
                  <td className="mono">{(rule as Json).tools.join(" · ")}</td>
                  <td>
                    {role === "employee"
                      ? "公共资料"
                      : "非公共资料还需要逐文档授权"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="policy-notes">
          <span>
            <CheckCircle2 size={16} /> 所有导出均需独立审批
          </span>
          <span>
            <CheckCircle2 size={16} /> 未明确允许的操作默认拒绝
          </span>
          <span>
            <CheckCircle2 size={16} /> 审批权与业务数据权分离
          </span>
        </div>
      </section>
      <div className="business-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>执行约束</h2>
            <LockKeyhole size={18} />
          </div>
          <dl className="limits">
            {Object.entries(view.policy.limits).map(([k, v]) => (
              <div key={k}>
                <dt>
                  {
                    (
                      {
                        max_steps: "最大工具调用步数",
                        task_timeout_seconds: "活跃任务超时（秒）",
                        max_retries: "执行失败后最多重试",
                        approval_ttl_seconds: "审批有效期（秒）",
                      } as Json
                    )[k]
                  }
                </dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
          </dl>
          <div className="destination-box">
            <span className="eyebrow">DESTINATION ALLOWLIST</span>
            {view.policy.destinations.map((d: string) => (
              <code key={d}>{d}</code>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>结构化策略</h2>
            <span className="subtle">{canEdit ? "管理员可编辑" : "只读"}</span>
          </div>
          <textarea
            className="code-editor"
            aria-label="策略 JSON"
            readOnly={!canEdit}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {canEdit && (
            <div className="panel-footer">
              <button className="primary" disabled={busy} onClick={save}>
                校验并保存新版本
              </button>
            </div>
          )}
        </section>
      </div>
      {canEdit && access && (
        <section className="panel">
          <div className="panel-heading">
            <h2>合成环境授权管理</h2>
            <span className="subtle">撤销权限及资源版本变更实验</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>授权文档</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {access.grants.map((g: Json) => (
                  <tr key={g.user_id + g.document_id}>
                    <td>{g.user_id}</td>
                    <td className="mono">{g.document_id}</td>
                    <td>
                      <button className="text-button" onClick={() => revoke(g)}>
                        撤销授权
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="version-tools">
            {access.documents.map((d: Json) => (
              <button
                className="secondary"
                key={d.id}
                onClick={() => bump(d.id)}
              >
                {d.id} v{d.version} → v{d.version + 1}
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function AuditPanel({
  identity,
  notify,
}: {
  identity: Identity;
  notify: (s: string) => void;
}) {
  const [rows, setRows] = useState<Json[]>([]),
    [filters, setFilters] = useState({
      task_id: "",
      user_id: "",
      tool: "",
      decision: "",
    }),
    [error, setError] = useState("");
  async function load(older = false) {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    if (older && rows.length)
      q.set("before", String(rows[rows.length - 1].seq));
    const result = await api("/audit?" + q);
    setRows(older ? [...rows, ...result] : result);
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <h2>审计事件流</h2>
          <span className="subtle">
            {identity.user.privileges.includes("audit_all")
              ? "全局元数据可见"
              : "仅本人操作可见"}
          </span>
        </div>
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            load().catch((e) => setError(e.message));
          }}
        >
          <input
            aria-label="按任务 ID 筛选"
            placeholder="任务 ID"
            value={filters.task_id}
            onChange={(e) =>
              setFilters({ ...filters, task_id: e.target.value })
            }
          />
          {identity.user.privileges.includes("audit_all") && (
            <input
              aria-label="按用户筛选"
              placeholder="用户 ID"
              value={filters.user_id}
              onChange={(e) =>
                setFilters({ ...filters, user_id: e.target.value })
              }
            />
          )}
          <select
            aria-label="按工具筛选"
            value={filters.tool}
            onChange={(e) => setFilters({ ...filters, tool: e.target.value })}
          >
            <option value="">所有工具</option>
            {["read_document", "create_ticket", "export_report"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <select
            aria-label="按决策筛选"
            value={filters.decision}
            onChange={(e) =>
              setFilters({ ...filters, decision: e.target.value })
            }
          >
            <option value="">所有决策</option>
            <option value="allow">允许</option>
            <option value="deny">拒绝</option>
            <option value="pending">待审批</option>
          </select>
          <button className="primary">筛选</button>
          {identity.user.privileges.includes("audit_all") && (
            <button
              type="button"
              className="secondary"
              onClick={() =>
                api("/audit/verify")
                  .then((r) =>
                    notify(
                      `审计链${r.valid ? "验证通过" : "校验失败"}，已检查 ${r.checked} 条记录。`,
                    ),
                  )
                  .catch((e) => setError(e.message))
              }
            >
              校验哈希链
            </button>
          )}
        </form>
        {error && <div className="error">{error}</div>}
        <div className="table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th>序号 / 时间</th>
                <th>事件 / 工具</th>
                <th>身份</th>
                <th>决策</th>
                <th>原因</th>
                <th>证据</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <React.Fragment key={r.seq}>
                  <tr>
                    <td>
                      <strong>#{r.seq}</strong>
                      <small>{time(r.timestamp)}</small>
                    </td>
                    <td>
                      <strong className="mono">{r.event}</strong>
                      <small>{r.tool || "系统事件"}</small>
                    </td>
                    <td>{r.user_id || "未认证"}</td>
                    <td>
                      <Badge status={r.decision} />
                    </td>
                    <td className="mono reason-cell">{r.reason}</td>
                    <td>
                      <details>
                        <summary>详情</summary>
                        <Code value={r} />
                      </details>
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && <Empty>没有匹配的审计事件。</Empty>}
        <div className="panel-footer">
          <span className="fine-print">
            正文不写入普通日志。哈希链可检查一致性，不能抵御拥有数据库文件权限的管理员重写整个链。
          </span>
          {rows.length >= 200 && (
            <button
              className="secondary"
              onClick={() => load(true).catch((e) => setError(e.message))}
            >
              加载更早记录
            </button>
          )}
        </div>
      </section>
    </>
  );
}

function RunComparison({ runs, current }: { runs: Json[]; current: Json }) {
  const [otherId, setOtherId] = useState("");
  const candidates = runs.filter((r) => r.result && r.id !== current.id);
  const other = candidates.find((r) => r.id === otherId) || candidates[0];
  if (!other)
    return (
      <section className="panel">
        <div className="panel-heading">
          <h2>历史版本对比</h2>
        </div>
        <Empty>
          完成第二次评测后，可比较模型、数据集、策略版本及 C 配置指标。
        </Empty>
      </section>
    );
  const same =
    current.result.dataset_hash === other.result.dataset_hash &&
    current.result.model_id === other.result.model_id;
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>历史版本对比 · C 配置</h2>
        <select
          aria-label="对比评测版本"
          value={other.id}
          onChange={(e) => setOtherId(e.target.value)}
        >
          {candidates.map((r) => (
            <option key={r.id} value={r.id}>
              {time(r.created_at)} · {r.config.split}
            </option>
          ))}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>运行</th>
              <th>模型 / 数据集</th>
              <th>策略 / 代码版本</th>
              <th>越权执行率</th>
              <th>正常完成率</th>
              <th>端到端 p50</th>
            </tr>
          </thead>
          <tbody>
            {[current, other].map((r, i) => (
              <tr key={r.id}>
                <td>
                  {i === 0 ? "当前选择" : "对比运行"}
                  <small>{time(r.created_at)}</small>
                </td>
                <td>
                  {r.result.model_id}
                  <small className="mono">{short(r.result.dataset_hash)}</small>
                </td>
                <td className="mono">
                  {short(r.result.policy_version)}
                  <small>{short(r.result.source_hash || "未记录")}</small>
                </td>
                <td>
                  {(
                    r.result.metrics.C.unauthorized_execution_rate * 100
                  ).toFixed(1)}
                  %
                </td>
                <td>
                  {(r.result.metrics.C.normal_completion_rate * 100).toFixed(1)}
                  %
                </td>
                <td>{r.result.metrics.C.end_to_end_p50_ms.toFixed(2)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-footer">
        <span className="fine-print">
          {same
            ? "模型与数据集一致；结合策略、代码版本及重复次数解释差异。"
            : "两次运行的模型或数据集不同，指标差异不能直接归因于策略改进。"}
        </span>
      </div>
    </section>
  );
}

function EvalPanel({ notify }: { notify: (s: string) => void }) {
  const [runs, setRuns] = useState<Json[]>([]),
    [selected, setSelected] = useState(""),
    [split, setSplit] = useState("dev"),
    [repeats, setRepeats] = useState("1"),
    [scope, setScope] = useState("all"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function load() {
    const data = await api("/evaluations");
    setRuns(data);
    return data;
  }
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);
  const running = runs.some((r) => r.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(
      () => load().catch((e) => setError(e.message)),
      1500,
    );
    return () => clearInterval(timer);
  }, [running]);
  async function run() {
    setBusy(true);
    setError("");
    try {
      const result = await api("/evaluations", {
        split,
        repeats: Number(repeats),
        provider: "mock",
      });
      setSelected(result.id);
      await load();
      notify("独立评测进程已启动，结果按实际业务状态计算。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const current = runs.find((r) => r.id === selected) || runs[0],
    report = current?.result;
  const shownMetrics =
    scope === "all"
      ? report?.metrics
      : report?.metric_groups?.[scope] || report?.metrics;
  const pct = (v: number | null) =>
    v == null ? "未测" : `${(v * 100).toFixed(1)}%`;
  return (
    <>
      <div className="info-banner">
        <FlaskConical size={22} />
        <div>
          <strong>同一模型、同一任务集，比较三种实验配置</strong>
          <p>
            A 普通 Agent · B 安全提示词 · C
            安全网关。每个案例使用独立合成数据库；Mock
            结果不代表真实模型抗攻击能力。
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>运行评测</h2>
          <span className="badge green">
            <span className="dot" /> Mock · 本地零模型费用
          </span>
        </div>
        <div className="eval-controls">
          <label>
            测试集
            <select
              aria-label="测试集"
              value={split}
              onChange={(e) => setSplit(e.target.value)}
            >
              <option value="dev">开发集 · 20 正常 + 20 对抗</option>
              <option value="holdout">保留集 · 8 正常 + 8 对抗</option>
            </select>
          </label>
          <label>
            重复次数
            <select
              value={repeats}
              onChange={(e) => setRepeats(e.target.value)}
              aria-label="重复次数"
            >
              <option>1</option>
              <option>2</option>
              <option>3</option>
            </select>
          </label>
          <button className="primary" disabled={busy || running} onClick={run}>
            {running ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Play size={16} />
            )}{" "}
            {running ? "正在隔离环境评测" : "运行 A / B / C"}
          </button>
          <label className="run-select">
            历史运行
            <select
              aria-label="历史评测"
              value={current?.id || ""}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">选择一次运行</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {time(r.created_at)} · {r.config.split} ·{" "}
                  {states[r.status] || r.status}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        {current && (
          <div className="eval-meta">
            <Badge status={current.status} />
            <code>{current.id}</code>
            {current.error && <span className="error">{current.error}</span>}
          </div>
        )}
      </section>
      {report ? (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>实测结果</h2>
              <span className="subtle">
                {report.model_id} · {report.sample_count} 个案例 ·{" "}
                {report.repeats} 次重复
              </span>
              <select
                aria-label="指标范围"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
              >
                <option value="all">全部案例（含协议探针）</option>
                <option value="agent">仅 Agent 案例</option>
                <option value="protocol">仅协议探针</option>
              </select>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>配置</th>
                    <th>未授权操作实际执行率 ↓</th>
                    <th>正常任务完成率 ↑</th>
                    <th>正常请求误拦截率 ↓</th>
                    <th>网关额外耗时 p50</th>
                    <th>端到端 p50</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(shownMetrics).map(([mode, m]) => (
                    <tr
                      key={mode}
                      className={mode === "C" ? "highlight-row" : ""}
                    >
                      <td>
                        <strong>
                          {mode} ·{" "}
                          {
                            { A: "普通 Agent", B: "安全提示词", C: "安全网关" }[
                              mode
                            ]
                          }
                        </strong>
                        <small>
                          对抗 n={(m as Json).attack_n} · 正常 n=
                          {(m as Json).normal_n}
                        </small>
                      </td>
                      <td>{pct((m as Json).unauthorized_execution_rate)}</td>
                      <td>{pct((m as Json).normal_completion_rate)}</td>
                      <td>{pct((m as Json).false_block_rate)}</td>
                      <td>
                        {(m as Json).gateway_overhead_p50_ms == null
                          ? "不适用"
                          : `${(m as Json).gateway_overhead_p50_ms.toFixed(2)} ms`}
                      </td>
                      <td>
                        {(m as Json).end_to_end_p50_ms == null
                          ? "未测"
                          : `${(m as Json).end_to_end_p50_ms.toFixed(2)} ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel-footer">
              <span className="fine-print">
                攻击成功依据 read_receipts / tickets / inbox
                的实际状态。端到端耗时包含协议动作，等待人工审批时间不纳入此自动评测。
              </span>
            </div>
          </section>
          <div className="business-grid">
            <section className="panel">
              <div className="panel-heading">
                <h2>审批处理结果</h2>
              </div>
              <Code value={report.approval_outcomes} />
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>实验配置与边界</h2>
              </div>
              <Code
                value={{
                  dataset_hash: report.dataset_hash,
                  policy_version: report.policy_version,
                  seed_version: report.seed_version,
                  provider: report.provider,
                  repeats: report.repeats,
                  real_model: "未测",
                  protocol_cases: report.protocol_cases,
                }}
              />
            </section>
          </div>
          <RunComparison runs={runs} current={current} />
          <section className="panel">
            <div className="panel-heading">
              <h2>案例与失败证据</h2>
              <span className="subtle">保留全部运行，包括未达预期结果</span>
            </div>
            <div className="case-list">
              {report.cases.map((c: Json, i: number) => (
                <details key={i}>
                  <summary>
                    <span className="mono">
                      {c.mode} / {c.case_id}
                    </span>
                    <span>{c.category}</span>
                    <Badge status={c.passed ? "completed" : "failed"} />
                    <span className="subtle">
                      {c.unauthorized
                        ? "存在未授权实际操作"
                        : "无未授权实际操作"}
                    </span>
                  </summary>
                  <Code value={c} />
                </details>
              ))}
            </div>
          </section>
        </>
      ) : (
        <section className="panel">
          <Empty>
            {running
              ? "正在执行案例，请稍候。页面会自动更新。"
              : "尚未选择已完成的评测。真实模型指标保持“未测”。"}
          </Empty>
        </section>
      )}
    </>
  );
}

function App() {
  const [identity, setIdentity] = useState<Identity | null>(null),
    [loading, setLoading] = useState(true),
    [tab, setTab] = useState<Tab>("agent"),
    [toast, setToast] = useState("");
  const refreshIdentity = async () => {
    const i = await api<Identity>("/session");
    csrf = i.csrf;
    setIdentity(i);
  };
  useEffect(() => {
    refreshIdentity()
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 8000);
    return () => clearTimeout(timer);
  }, [toast]);
  if (loading)
    return (
      <div className="loading">
        <ShieldCheck size={34} />
        <p>正在验证会话…</p>
      </div>
    );
  if (!identity)
    return (
      <LoginView
        onLogin={(i) => {
          csrf = i.csrf;
          setIdentity(i);
          setTab("agent");
        }}
      />
    );
  const tabs = [
    {
      id: "agent",
      label: "Agent 工作台",
      en: "WORKSPACE",
      icon: TerminalSquare,
    },
    {
      id: "approvals",
      label: "审批中心",
      en: "APPROVALS",
      icon: ClipboardCheck,
    },
    {
      id: "policy",
      label: "策略与权限",
      en: "POLICIES",
      icon: SlidersHorizontal,
    },
    { id: "audit", label: "审计记录", en: "AUDIT TRAIL", icon: ScrollText },
    { id: "eval", label: "评测实验室", en: "EVALUATION", icon: FlaskConical },
  ].filter(
    (t) => t.id !== "eval" || identity.user.privileges.includes("evaluate"),
  );
  const active = tabs.find((t) => t.id === tab) || tabs[0];
  async function logout() {
    try {
      await api("/auth/logout", {});
      csrf = "";
      setIdentity(null);
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">
            <ShieldCheck />
          </span>
          <div>
            TOOL GUARD<small>Agent Security Gateway</small>
          </div>
        </div>
        <div className="workspace-label">
          合成企业工作空间 <span>LOCAL</span>
        </div>
        <nav aria-label="主导航">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "active" : ""}
              onClick={() => setTab(t.id as Tab)}
            >
              <t.icon size={19} />
              <span>{t.label}</span>
              {tab === t.id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-boundary">
          <ShieldCheck size={22} />
          <strong>边界清楚，决策可查。</strong>
          <p>
            控制策略禁止的操作，
            <br />
            不宣称防御所有提示注入。
          </p>
          <span>DETERMINISTIC BY DESIGN</span>
        </div>
        <div className="identity-block">
          <div className="avatar">{identity.user.name[0]}</div>
          <div>
            <strong>{identity.user.name.split(" · ")[0]}</strong>
            <small>
              {identity.user.id} · {roles[identity.user.role]}
            </small>
          </div>
          <button title="退出登录" aria-label="退出登录" onClick={logout}>
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span>工作空间</span>
            <span className="slash">/</span>
            <strong>{active.label}</strong>
          </div>
          <div className="inline">
            <span className="environment">
              <span className="dot" /> 合成环境在线
            </span>
            <span className="top-version">v0.1</span>
          </div>
        </header>
        <main>
          <div className="page-title">
            <div>
              <span className="eyebrow">{active.en}</span>
              <h1>{active.label}</h1>
              <p>
                {
                  {
                    agent:
                      "让任务继续，让越权止步。查看一次真实的授权与执行过程。",
                    approvals: "每一次高风险操作，都需要一份精确且有效的授权。",
                    policy: "将权限写成规则，而不是寄托在模型的承诺中。",
                    audit: "从模型建议到实际副作用，重建每一步决策。",
                    eval: "用可验证的业务状态衡量安全性，而非模型自述。",
                  }[tab]
                }
              </p>
            </div>
            <div className="identity-pill">
              <Fingerprint size={17} />
              {identity.user.name.split(" · ")[1]}
            </div>
          </div>
          <div className="boundary-strip">
            <LockKeyhole size={15} />
            <span>当前身份来自后端会话</span>
            <span className="divider" />
            <span>{identity.access.documents.length} 项可读资源</span>
            <span className="divider" />
            <span>导出必须审批</span>
            <code>{short(identity.access.version)}</code>
          </div>
          {tab === "agent" && (
            <AgentPanel
              key={identity.user.id}
              identity={identity}
              notify={setToast}
            />
          )}{" "}
          {tab === "approvals" && (
            <ApprovalPanel identity={identity} notify={setToast} />
          )}{" "}
          {tab === "policy" && (
            <PolicyPanel
              identity={identity}
              refreshIdentity={refreshIdentity}
              notify={setToast}
            />
          )}{" "}
          {tab === "audit" && (
            <AuditPanel identity={identity} notify={setToast} />
          )}{" "}
          {tab === "eval" && <EvalPanel notify={setToast} />}
          <footer className="page-footer">
            <span>Agent Tool Guard</span>
            <span>合成数据 · 可信后端 · 可追踪执行</span>
            <span>v0.1.0</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          <span>{toast}</span>
          <button aria-label="关闭提示" onClick={() => setToast("")}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
