# 第三方组件说明

项目源码建议并采用 MIT；第三方组件保留各自许可证。以下信息从已锁定、实际安装的包元数据提取。完整许可证以各包内 LICENSE 为准。

运行时不下载字体、图像或第三方 UI 内容。界面采用系统字体，截图来自本地合成应用。Python 自带 SQLite；SQLite 为 public domain，Python 按 PSF license 分发。没有内置模型权重。OpenAI 是可选外部 API，使用时适用其服务条款。

## Python（包含测试与审计工具）

| 包 | 锁定版本 | 元数据许可证 |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| boolean.py | 5.0 | BSD-2-Clause |
| CacheControl | 0.14.4 | Apache-2.0 |
| certifi | 2026.10.23 | MPL-2.0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| colorama | 0.4.6 | See package LICENSE |
| coverage | 7.17.2 | Apache-2.0 |
| cyclonedx-python-lib | 11.12.0 | Apache-2.0 |
| defusedxml | 0.7.1 | PSFL |
| fastapi | 0.162.2 | MIT |
| filelock | 4.2.10 | MIT |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| license-expression | 30.4.4 | Apache-2.0 |
| markdown-it-py | 4.2.0 | See package LICENSE |
| mdurl | 0.1.2 | See package LICENSE |
| msgpack | 1.2.4 | Apache-2.0 |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| packageurl-python | 0.17.6 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pip | 26.3 | MIT |
| pip-requirements-parser | 32.0.1 | MIT |
| pip_api | 0.0.35 | Apache License |
| pip_audit | 2.10.1 | See package LICENSE |
| platformdirs | 4.14.5 | MIT |
| pluggy | 1.7.0 | MIT |
| py-serializable | 2.2.0 | Apache-2.0 |
| pydantic | 2.14.3 | MIT |
| pydantic_core | 2.50.4 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pyparsing | 3.3.3 | MIT |
| pytest | 9.2.0 | MIT |
| pytest-cov | 6.1.1 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| rich | 15.0.0 | MIT |
| ruff | 0.11.13 | MIT |
| setuptools | 84.2.1 | MIT |
| sortedcontainers | 2.4.0 | Apache 2.0 |
| starlette | 1.10.0 | BSD-3-Clause |
| tomli | 2.5.0 | MIT |
| tomli_w | 1.2.0 | See package LICENSE |
| typing-inspection | 0.4.5 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |

## npm（包含构建与浏览器测试工具）

| 包 | 锁定版本 | 元数据许可证 |
|---|---|---|
| @oxc-project/types | 0.156.0 | MIT |
| @playwright/test | 1.65.0 | Apache-2.0 |
| @rolldown/binding-android-arm-eabi | 1.2.18 | MIT |
| @rolldown/binding-android-arm64 | 1.2.18 | MIT |
| @rolldown/binding-darwin-arm64 | 1.2.18 | MIT |
| @rolldown/binding-darwin-x64 | 1.2.18 | MIT |
| @rolldown/binding-freebsd-x64 | 1.2.18 | MIT |
| @rolldown/binding-linux-arm-gnueabihf | 1.2.18 | MIT |
| @rolldown/binding-linux-arm64-gnu | 1.2.18 | MIT |
| @rolldown/binding-linux-arm64-musl | 1.2.18 | MIT |
| @rolldown/binding-linux-ppc64-gnu | 1.2.18 | MIT |
| @rolldown/binding-linux-s390x-gnu | 1.2.18 | MIT |
| @rolldown/binding-linux-x64-gnu | 1.2.18 | MIT |
| @rolldown/binding-linux-x64-musl | 1.2.18 | MIT |
| @rolldown/binding-openharmony-arm64 | 1.2.18 | MIT |
| @rolldown/binding-win32-arm64-msvc | 1.2.18 | MIT |
| @rolldown/binding-win32-x64-msvc | 1.2.18 | MIT |
| @rolldown/pluginutils | 1.1.0 | MIT |
| @types/react | 19.2.14 | MIT |
| @types/react-dom | 19.2.3 | MIT |
| @typescript/typescript-aix-ppc64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-darwin-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-darwin-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-freebsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-freebsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-arm | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-loong64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-mips64el | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-ppc64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-riscv64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-s390x | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-netbsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-netbsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-openbsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-openbsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-sunos-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-win32-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-win32-x64 | 7.0.2 | Apache-2.0 |
| @vitejs/plugin-react | 6.3.0 | MIT |
| agent-browser | 0.41.2 | Apache-2.0 |
| csstype | 3.2.3 | MIT |
| detect-libc | 2.1.2 | Apache-2.0 |
| fdir | 6.5.0 | MIT |
| fsevents | 2.3.3 | MIT |
| lightningcss | 1.33.0 | MPL-2.0 |
| lightningcss-android-arm64 | 1.33.0 | MPL-2.0 |
| lightningcss-darwin-arm64 | 1.33.0 | MPL-2.0 |
| lightningcss-darwin-x64 | 1.33.0 | MPL-2.0 |
| lightningcss-freebsd-x64 | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm-gnueabihf | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm64-gnu | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm64-musl | 1.33.0 | MPL-2.0 |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 |
| lightningcss-linux-x64-musl | 1.33.0 | MPL-2.0 |
| lightningcss-win32-arm64-msvc | 1.33.0 | MPL-2.0 |
| lightningcss-win32-x64-msvc | 1.33.0 | MPL-2.0 |
| lucide-react | 0.468.0 | ISC |
| nanoid | 3.3.20 | MIT |
| picocolors | 1.1.1 | ISC |
| picomatch | 4.0.7 | MIT |
| playwright | 1.65.0 | Apache-2.0 |
| playwright-core | 1.65.0 | Apache-2.0 |
| postcss | 8.5.32 | MIT |
| prettier | 3.9.10 | MIT |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| rolldown | 1.2.18 | MIT |
| scheduler | 0.28.0 | MIT |
| source-map-js | 1.2.2 | BSD-3-Clause |
| tinyglobby | 0.2.17 | MIT |
| typescript | 7.0.2 | Apache-2.0 |
| vite | 8.3.7 | MIT |
