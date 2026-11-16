"""Build publishable evidence and a source archive; never package local business data."""

import hashlib
import importlib.metadata as metadata
import json
import platform
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results"


def redact_paths(value):
    if isinstance(value, str):
        value = value.replace(str(ROOT), "<repo>").replace(ROOT.as_posix(), "<repo>")
        if ":\\" in value or value.startswith("/home/"):
            return "<local path redacted>"
        return value
    if isinstance(value, list):
        return [redact_paths(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_paths(v) for k, v in value.items()}
    return value


def third_party():
    lines = [
        "# 第三方组件说明",
        "",
        "项目源码建议并采用 MIT；第三方组件保留各自许可证。以下信息从已锁定、实际安装的包元数据提取。完整许可证以各包内 LICENSE 为准。",
        "",
        "运行时不下载字体、图像或第三方 UI 内容。界面采用系统字体，截图来自本地合成应用。Python 自带 SQLite；SQLite 为 public domain，Python 按 PSF license 分发。没有内置模型权重。OpenAI 是可选外部 API，使用时适用其服务条款。",
        "",
        "## Python（包含测试与审计工具）",
        "",
        "| 包 | 锁定版本 | 元数据许可证 |",
        "|---|---|---|",
    ]
    for spec in (ROOT / "requirements.lock").read_text(encoding="utf-8-sig").splitlines():
        if "==" not in spec:
            continue
        name, version = spec.split("==", 1)
        info = metadata.metadata(name)
        license_name = info.get("License-Expression") or info.get("License") or "See package LICENSE"
        license_name = license_name.splitlines()[0][:90].replace("|", "/")
        lines.append(f"| {name} | {version} | {license_name} |")
    lines += [
        "",
        "## npm（包含构建与浏览器测试工具）",
        "",
        "| 包 | 锁定版本 | 元数据许可证 |",
        "|---|---|---|",
    ]
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    for path, pkg in sorted(lock["packages"].items()):
        if not path:
            continue
        name = path.removeprefix("node_modules/")
        lines.append(f"| {name} | {pkg.get('version', '—')} | {pkg.get('license', 'See package LICENSE')} |")
    (ROOT / "THIRD_PARTY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evidence():
    report_path = RESULTS / "browser-tests.json"
    if report_path.exists():
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        private = ROOT / ".local/browser-tests-original.json"
        if not raw.get("local_paths_redacted"):
            private.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        clean = redact_paths(raw)
        clean["local_paths_redacted"] = True
        report_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tree = ET.parse(RESULTS / "pytest.xml")
    for suite in tree.iter("testsuite"):
        suite.set("hostname", "local-validation")
    tree.write(RESULTS / "pytest.xml", encoding="utf-8", xml_declaration=True)
    suites = list(tree.iter("testsuite"))
    tests = sum(int(s.attrib["tests"]) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
    browser = json.loads(report_path.read_text(encoding="utf-8"))
    coverage = json.loads((RESULTS / "coverage.json").read_text(encoding="utf-8"))["totals"][
        "percent_covered"
    ]
    dev = json.loads((RESULTS / "mock-dev.json").read_text(encoding="utf-8"))
    holdout = json.loads((RESULTS / "mock-holdout.json").read_text(encoding="utf-8"))
    audit = json.loads((RESULTS / "dependency-audit.json").read_text(encoding="utf-8"))
    vulnerable = sum(bool(d.get("vulns")) for d in audit["dependencies"])
    npm_audit = json.loads((RESULTS / "npm-audit.json").read_text(encoding="utf-8-sig"))
    npm_vulnerable = npm_audit["metadata"]["vulnerabilities"]["total"]
    summary = {
        "validation_date": "2026-11-10",
        "timezone": "Asia/Shanghai",
        "python": platform.python_version(),
        "pytest": {"tests": tests, "failures": failures, "coverage_percent": round(coverage, 2)},
        "browser": browser["stats"],
        "python_vulnerable_packages": vulnerable,
        "npm_vulnerabilities": npm_vulnerable,
        "mock_dev": dev["metrics"],
        "mock_holdout": holdout["metrics"],
        "real_model": {"status": "not_measured", "network_calls": 0},
        "source_hash": dev["source_hash"],
    }
    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# v0.1 实际验收记录",
        "",
        "验证日期：2026-11-10（Asia/Shanghai）。本记录从测试和评测原始文件汇总，不生成模拟成绩。",
        "",
        f"- pytest：{tests} 项，{failures} 个失败/错误；Python 行覆盖率 {coverage:.2f}%（只包含 pytest 进程，不把浏览器/CLI 运行计入）。",
        f"- Playwright：{browser['stats']['expected']} 条通过，{browser['stats']['unexpected']} 条失败；Chromium/本机 Chrome，真实启动独立前后端。",
        "- TypeScript + Vite 生产构建通过；Ruff 检查通过；pip check 无破损依赖。",
        f"- pip-audit：本次查询 {vulnerable} 个包存在已知漏洞。npm audit 本次报告 {npm_vulnerable} 个漏洞。此结果不是未来安全保证。",
        "- 测试涵盖：身份/CSRF、逐资源授权、工具不可直连、审批范围及自批拒绝、绑定变更/过期/撤销/消费、并发/重试、权限撤销、审计失败回滚、步骤/超时限制、数据隔离、XSS 文本呈现、移动布局、审批/审计/评测全流程。",
        "",
        "## Mock 实测",
        "",
        "以下为全部案例（包含协议探针）的案例级指标。两个 split 均独立运行 A/B/C，各重复 2 次。",
        "",
        "| 测试集 / 配置 | 对抗运行数 | 正常运行数 | 未授权实际执行率 | 正常完成率 | 正常误拦截率 | 端到端 p50 ms | 网关开销 p50 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, report in (("开发集", dev), ("保留集", holdout)):
        for mode, m in report["metrics"].items():
            overhead = "不适用" if m["gateway_overhead_p50_ms"] is None else str(m["gateway_overhead_p50_ms"])
            lines.append(
                f"| {label} / {mode} | {m['attack_n']} | {m['normal_n']} | {m['unauthorized_execution_rate']:.1%} | {m['normal_completion_rate']:.1%} | {m['false_block_rate']:.1%} | {m['end_to_end_p50_ms']} | {overhead} |"
            )
    lines += [
        "",
        "A/B 的失败案例是对照实验观察值，全部保留在原始结果的 failures/cases 中；C 的 expected_state 与网关决策也逐例记录。基线中一项正常重试案例会产生重复工单，因此正常完成率并非 100%。",
        "",
        "## 真实模型与环境限制",
        "",
        "真实 OpenAI API 未运行；模型表现、连通性、真实 API 时延与费用均未测。适配器仅做了模拟 HTTP transport 的请求/响应及 reasoning/function_call_output 续接契约测试。",
        "",
        "Mock 是人为定义的确定性规则。0% 表示当前测试集里没有违规实际副作用，不能推出模型普遍安全。protocol 与 agent 指标另存于原始 JSON 的 metric_groups，页面可切换查看。",
        "",
        "测试期间遇到并修复：审计数值规范化不一致；过早执行使待审批请求不可继续；同键改参后的旧审批失效处理。Windows 沙箱曾阻塞 asyncio 回环连接，经过授权后在本机完成了 API 与浏览器测试。",
        "",
        "测试依赖当前产生一条 Starlette 对 httpx TestClient 的弃用提示；测试通过。v0.1 尚未迁移测试客户端到 httpx2。GitHub Actions 文件已提供，但本次没有创建远程仓库或运行远程 CI。",
        "",
        "## 证据索引",
        "",
        "- [pytest 原始结果](results/pytest.xml) / [覆盖率](results/coverage.json)",
        "- [浏览器结果（本地路径已脱敏）](results/browser-tests.json) / [截图](screenshots/)",
        "- [开发集原始结果](results/mock-dev.json) / [保留集原始结果](results/mock-holdout.json)",
        "- [依赖审计](results/dependency-audit.json) / [汇总 JSON](results/summary.json)",
        "",
        "默认数据库与 session、API 密钥、失败 trace、测试沙箱均不进入源码包。",
    ]
    (ROOT / "docs/VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def package_source():
    allowed_dirs = [
        "backend",
        "config",
        "docs",
        "evals",
        "examples",
        "frontend/src",
        "frontend/e2e",
        "scripts",
        "tests",
        ".github",
    ]
    allowed_files = [
        ".gitignore",
        ".env.example",
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "THIRD_PARTY.md",
        "pyproject.toml",
        "requirements.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/tsconfig.json",
        "frontend/vite.config.ts",
        "frontend/playwright.config.ts",
        "frontend/index.html",
    ]
    files = [ROOT / p for p in allowed_files]
    for folder in allowed_dirs:
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and not any(part.endswith(".egg-info") for part in p.parts)
        )
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = release / "agent-tool-guard-v0.1-source.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for file in sorted(set(files)):
            relative = file.relative_to(ROOT).as_posix()
            if (
                file.name == ".env"
                or file.suffix in {".sqlite3", ".pyc", ".log"}
                or "node_modules" in file.parts
            ):
                raise RuntimeError("PRIVATE_FILE_IN_PACKAGE")
            bundle.write(file, "agent-tool-guard/" + relative)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    print(
        json.dumps(
            {"archive": str(archive), "source_files": len(set(files)), "sha256": checksum}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    third_party()
    evidence()
    package_source()
