# Agent Tool Guard

**Agent 工具调用安全网关与评测平台 · v0.1**

模型提出工具调用，可信后端验证身份、具体资源权限、参数和审批状态，再决定允许、拒绝或等待审批。这个项目保护的是**策略禁止的操作**；它不是提示注入检测器，也不宣称能防御所有提示注入。

> A reusable authorization gateway and synthetic enterprise-agent lab. It combines resource-level access control, approval binding, atomic local effects, structured audit trails, and state-based A/B/C evaluation. Mock results and real-model experiments are explicitly separated.

![恶意文档诱导后的拒绝](docs/screenshots/browser-injection.png)

## 可以实际演示什么

- 员工读取公共制度、创建并查看自己的工单；研发与 HR 还需要逐文档授权。
- Mock 读到合成恶意文档后确实提出越权读取；网关拒绝，业务读取记录中不会出现被禁止文档。
- 导出先进入审批中心，独立审批人批准后，由发起人继续执行，结果写入本地模拟收件箱。
- 修改参数、资源版本、策略版本或权限后，旧审批无法继续授权操作。
- 同一幂等键重试或并发执行只产生一个副作用；执行异常会回滚业务写入与审批消费。
- 查看调用轨迹、拒绝原因、策略版本、审批关联、耗时与审计哈希链。
- 在独立进程及独立数据库中比较 A 普通 Agent、B 安全提示词、C 安全网关。

## 本地启动：Windows PowerShell

环境要求：Python 3.11+（本机验证 3.12）、Node.js 22.12+（本机验证 24）、npm。当前目录应为本仓库根目录。

```powershell
# 首次安装；不覆盖已有 .env 或业务数据
.\scripts\Setup.ps1
# 如果 python 指向 Windows Store 占位程序，传入真实解释器：
.\scripts\Setup.ps1 -Python 'C:\实际安装路径\python.exe'
```

在两个 PowerShell 终端中分别运行：

```powershell
# 终端 1
.\scripts\Start-Backend.ps1
# 终端 2
.\scripts\Start-Frontend.ps1
```

打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)。API 文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。两个服务仅监听本机回环地址。

前端构建后也可由 FastAPI 提供静态文件：

```powershell
Push-Location frontend
npm.cmd run build
Pop-Location
.\scripts\Start-Backend.ps1
# 打开 http://127.0.0.1:8000
```

| 测试账号 | 业务角色 | 独立管理权限 |
|---|---|---|
| employee | 普通员工 | 无 |
| engineer | 研发 | rd-001、rd-003 具体资源授权 |
| hr | HR | hr-001、hr-003 具体资源授权 |
| approver | 普通员工 | 审批 public / rd / hr 导出；没有额外正文访问权 |
| admin | 普通员工 | 策略/资源授权管理、全局元数据审计、评测 |

默认演示密码为 `Demo-Only-2026!`。所有账号、组织资料和人事内容都为合成数据。默认密码只适合本地演示。`ATG_DEMO_PASSWORD` 仅用于首次初始化；修改环境变量不会修改已经初始化的账号。

## 自动测试与评测

```powershell
.\scripts\Test.ps1

# 浏览器验收：自动启动独立端口 8010 / 5174 与专用测试数据库
Push-Location frontend
npm.cmd run test:e2e
Pop-Location

# 可重复的 Mock 实验
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m toolguard.cli evaluate --split dev --repeats 2 --output var/results/dev.json
.\.venv\Scripts\python.exe -m toolguard.cli evaluate --split holdout --repeats 2 --output var/results/holdout.json
```

浏览器测试默认使用本机 Chrome。CI 可设置 `PW_CHANNEL=chromium` 并安装 Playwright Chromium。`scripts/Test.ps1` 包括 pytest、Ruff 和 TypeScript/Vite 构建；浏览器测试单列，以便在有浏览器的环境中运行。

开发集为 **20 个正常 + 20 个对抗案例**；保留集为 **8 + 8**，文件及输入分开。结果由真实 SQLite 读取记录、工单和收件箱状态计算。审批协议探针不调用语言模型，并与 Agent 案例分别标记。所有失败案例和样本分母保留。

查看 [实际验收记录](docs/VALIDATION.md)、[评测方法与指标](docs/EVALUATION.md) 和 [原始实测结果](docs/results/)。**这些是确定性 Mock 模拟结果，真实模型实验尚未运行。**

## 真实 Tool Calling 配置

复制 `.env.example` 为 `.env`（安装脚本会自动完成），仅在本地设置：

```dotenv
OPENAI_API_KEY=在本地填写
OPENAI_MODEL=你的账号可用且支持Responses工具调用的模型标识
```

重启后端后，在工作台选择 OpenAI。模型标识不预设为“最新”，避免假定账号权限或模型可用性。适配器实现 OpenAI Responses API 的 function call → 网关 → function call output 循环；固定官方 API 地址，`store=false`，不提供 shell、通用 HTTP 或文件系统工具。**选择真实模型会把合成任务及已获授权的合成工具结果发给模型服务，并可能产生 API 费用。** 本次验收没有发送真实 API 请求。

真实模型评测必须从本地 CLI 显式开启：

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m toolguard.cli evaluate --provider openai --allow-paid-model --split dev --repeats 1 --output var/results/real-dev.json
```

真实模型评测仅运行 `scenario=agent` 的案例，协议探针由自动测试覆盖。适配器的报文结构与连续调用已用模拟 HTTP transport 测试；真实 API 连通性、模型表现和费用均未测。[官方 Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)

## 复用网关

推荐外部 Agent 使用 HTTP 接口。只有后端持有数据库和执行器；外部 Agent 不导入私有 executor，也不接收用户的会话凭据。由受信任的编排端持有会话，模型只返回工具名称和参数。

```python
from toolguard.client import GuardClient

client = GuardClient('http://127.0.0.1:8000')
client.login('employee', 'Demo-Only-2026!')
result = client.call('read_document', {'document_id': 'pub-001'},
                     idempotency_key='example-read-1')
print(result['status'], result['reason'])
client.close()
```

安装后可直接运行 [examples/integrate_agent.py](examples/integrate_agent.py)。HTTP `/api/gateway/call` 与后端 `Gateway.invoke(session_token, ToolRequest)` 是两个明确入口；客户端不能传入 role、user_id 或替代执行器。

## 目录

```text
backend/toolguard/
  auth.py             服务端身份、会话与独立审批权限
  schemas.py          严格参数和策略 schema
  policy.py           角色规则 + 逐文档授权 + 目的地名单
  gateway.py          决策、幂等、审批绑定、执行复核及事务
  executor.py         封闭的本地 SQLite 工具实现
  db.py               表结构、事务、审计哈希链
  models.py / agent.py 模型适配与有界任务编排
  api.py / client.py  FastAPI 与可复用客户端
  evaluation.py       独立业务状态 oracle 与 A/B/C runner
frontend/             React + TypeScript + Vite；Playwright 流程
config/policy.json    初始策略（经 Pydantic 校验）
evals/                开发与保留测试集
tests/                权限、审批、事务、隔离和模型契约测试
scripts/              PowerShell 启动、测试和材料生成
docs/                 架构、威胁模型、实现讲解与实测证据
var/                  本地业务数据库、评测沙箱（Git 忽略）
```

## 安全边界与已知限制

- 用户会话、策略管理者、后端代码和数据库宿主属于可信边界。能在后端宿主运行任意 Python 或修改数据库文件的人已越过该边界；私有 Python capability 不是 OS 沙箱。
- v0.1 的工具只进行 SQLite 合成业务操作，没有真实邮件、网络导出、系统命令或任意路径访问。模拟导出和审批消费可以在同一事务提交；接真实外部系统时必须另行设计 outbox、幂等消费及对账。
- 当前提供本地会话登录、CSRF 防护、HttpOnly/SameSite cookie、严格 Origin/Host、请求体上限及登录失败限速；没有企业 SSO、多租户、MFA、完整 DoS 防护、数据库加密或独立审计存储。不要直接暴露到公网。
- 审计默认不存文档正文、工单正文或模型回复。完整参数仅在后端业务/审批表中按需要保存；所有数据库文件和业务备份仍需宿主访问控制。
- 哈希链和 append-only trigger 用于一致性及篡改检查，不等于独立、不可抵赖的外部审计。
- 安全网关不能判断所有语义恶意行为：拥有合法权限的用户仍可能请求读取自己的敏感资料；合法工单中的攻击词语不会自动被封禁。
- SQLite 单写者事务适合本地演示与小规模验证。真实模型输出存在随机性；固定 Mock 和少量手写案例不能证明通用安全性。

## 继续阅读

- [架构、信任边界与状态机](docs/ARCHITECTURE.md)
- [威胁模型与权限矩阵](docs/THREAT_MODEL.md)
- [关键实现与面试讲解](docs/IMPLEMENTATION_GUIDE.md)
- [三分钟演示](docs/DEMO.md)
- [MCP 扩展设计](docs/MCP_DESIGN.md)
- [第三方依赖与许可证](THIRD_PARTY.md)

建议采用 MIT 方便代码复用；仓库已提供 [MIT LICENSE](LICENSE)。第三方组件保留各自许可证。此仓库材料仅准备本地发布，本次未创建公开 GitHub 仓库、未提交真实企业数据、未调用付费模型。
