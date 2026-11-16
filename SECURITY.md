# 安全问题与使用范围

v0.1 是仅监听本机的合成数据应用，不是可直接公网部署的企业产品。请先阅读 README 中的边界与 docs/THREAT_MODEL.md。

报告问题时请提供：版本、最小合成案例、初始角色/授权、预期与实际业务状态、去除正文和凭据后的 call/task ID。请不要在公开 Issue 中附带 API key、session cookie、真实企业数据或未脱敏数据库。

尚未建立公开维护者的私密披露渠道；实际发布前应由仓库所有者开启 GitHub private vulnerability reporting，并补充维护方式。不得把本地 `.env`、`var/`、`.local/`、浏览器 trace 或真实会话发布到 GitHub。
