# v0.1 实际验收记录

验证日期：2026-11-10（Asia/Shanghai）。本记录从测试和评测原始文件汇总，不生成模拟成绩。

- pytest：72 项，0 个失败/错误；Python 行覆盖率 81.61%（只包含 pytest 进程，不把浏览器/CLI 运行计入）。
- Playwright：4 条通过，0 条失败；Chromium/本机 Chrome，真实启动独立前后端。
- TypeScript + Vite 生产构建通过；Ruff 检查通过；pip check 无破损依赖。
- pip-audit：本次查询 0 个包存在已知漏洞。npm audit 本次报告 0 个漏洞。此结果不是未来安全保证。
- 测试涵盖：身份/CSRF、逐资源授权、工具不可直连、审批范围及自批拒绝、绑定变更/过期/撤销/消费、并发/重试、权限撤销、审计失败回滚、步骤/超时限制、数据隔离、XSS 文本呈现、移动布局、审批/审计/评测全流程。

## Mock 实测

以下为全部案例（包含协议探针）的案例级指标。两个 split 均独立运行 A/B/C，各重复 2 次。

| 测试集 / 配置 | 对抗运行数 | 正常运行数 | 未授权实际执行率 | 正常完成率 | 正常误拦截率 | 端到端 p50 ms | 网关开销 p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 开发集 / A | 40 | 40 | 90.0% | 95.0% | 0.0% | 8.447 | 不适用 |
| 开发集 / B | 40 | 40 | 80.0% | 95.0% | 0.0% | 8.383 | 不适用 |
| 开发集 / C | 40 | 40 | 0.0% | 100.0% | 0.0% | 9.718 | 9.236 |
| 保留集 / A | 16 | 16 | 75.0% | 87.5% | 0.0% | 8.194 | 不适用 |
| 保留集 / B | 16 | 16 | 62.5% | 87.5% | 0.0% | 8.674 | 不适用 |
| 保留集 / C | 16 | 16 | 0.0% | 100.0% | 0.0% | 14.201 | 9.476 |

A/B 的失败案例是对照实验观察值，全部保留在原始结果的 failures/cases 中；C 的 expected_state 与网关决策也逐例记录。基线中一项正常重试案例会产生重复工单，因此正常完成率并非 100%。

## 真实模型与环境限制

真实 OpenAI API 未运行；模型表现、连通性、真实 API 时延与费用均未测。适配器仅做了模拟 HTTP transport 的请求/响应及 reasoning/function_call_output 续接契约测试。

Mock 是人为定义的确定性规则。0% 表示当前测试集里没有违规实际副作用，不能推出模型普遍安全。protocol 与 agent 指标另存于原始 JSON 的 metric_groups，页面可切换查看。

测试期间遇到并修复：审计数值规范化不一致；过早执行使待审批请求不可继续；同键改参后的旧审批失效处理。Windows 沙箱曾阻塞 asyncio 回环连接，经过授权后在本机完成了 API 与浏览器测试。

测试依赖当前产生一条 Starlette 对 httpx TestClient 的弃用提示；测试通过。v0.1 尚未迁移测试客户端到 httpx2。GitHub Actions 文件已提供，但本次没有创建远程仓库或运行远程 CI。

## 证据索引

- [pytest 原始结果](results/pytest.xml) / [覆盖率](results/coverage.json)
- [浏览器结果（本地路径已脱敏）](results/browser-tests.json) / [截图](screenshots/)
- [开发集原始结果](results/mock-dev.json) / [保留集原始结果](results/mock-holdout.json)
- [依赖审计](results/dependency-audit.json) / [汇总 JSON](results/summary.json)

默认数据库与 session、API 密钥、失败 trace、测试沙箱均不进入源码包。
