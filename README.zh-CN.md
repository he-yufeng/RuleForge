[![English](https://img.shields.io/badge/lang-English-blue)](README.md)
[![PyPI version](https://img.shields.io/pypi/v/ruleforge)](https://pypi.org/project/ruleforge/)
[![CI](https://github.com/he-yufeng/RuleForge/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/RuleForge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

# RuleForge

**从代码库自动生成 AI 编程助手规则文件。**

RuleForge 扫描你的项目——编程语言、框架、lint 工具、测试配置、CI 设置——然后自动生成可直接使用的规则文件，支持 **Claude Code**（`CLAUDE.md`）、**Cursor**（`.cursorrules`）和 **GitHub Copilot**（`.github/copilot-instructions.md`）。

别再手写这些文件了，让你的代码库自己说话。

## 为什么需要？

AI 编程助手在有项目上下文时效果会好很多。但大多数开发者要么：

- 根本不写规则文件（白白浪费性能）
- 复制粘贴通用模板，跟实际技术栈完全不匹配
- 花 30 分钟手写一份，然后再也不更新

RuleForge 通过真正读取你的项目配置，几秒钟生成准确的、贴合技术栈的规则。

## 检测能力

| 类别 | 示例 |
|------|------|
| **编程语言** | Python、TypeScript、JavaScript、Go、Rust、Java、C++ 等 20+ 种 |
| **框架** | FastAPI、Flask、Django、React、Next.js、Vue、Svelte、Express、Gin、Axum... |
| **包管理器** | pip、poetry、hatch、pnpm、yarn、bun、npm、cargo |
| **Lint 和格式化** | ruff、black、eslint、prettier、biome、clippy、go fmt |
| **测试框架** | pytest、unittest、vitest、jest、mocha |
| **CI 系统** | GitHub Actions、GitLab CI、CircleCI、Jenkins |
| **其他** | Docker、Makefile、monorepo 结构、入口文件、.gitignore 模式 |

## 安装

```bash
pip install ruleforge
```

## 快速开始

```bash
# 扫描项目，查看检测结果
ruleforge scan .

# 生成所有规则文件（CLAUDE.md、.cursorrules、copilot-instructions）
ruleforge generate .

# 只生成 CLAUDE.md
ruleforge generate . -f claude

# 预览，不写文件
ruleforge preview .

# 覆盖已有文件
ruleforge generate . --overwrite

# 输出到其他目录
ruleforge generate . -o /tmp/rules
```

## 输出示例

对一个 FastAPI 项目运行 `ruleforge generate` 会生成类似这样的 `CLAUDE.md`：

```markdown
# my-api

This is a Python project.
Key frameworks: FastAPI, Pydantic, SQLAlchemy.

## Project Structure

Source directories: `src/`, `tests/`
Entry points: `main.py`
Package manager: poetry

## Coding Conventions

- Linter: ruff
- Formatter: ruff
- Testing: pytest
- Python: >=3.11
- CI: GitHub Actions

## Guidelines

- Use type hints for function signatures.
- Run `ruff check` and `ruff format` before committing.
- Write tests with pytest. Put test files in the `tests/` directory.
- Use Pydantic models for request/response schemas.
- The project uses Docker. Keep Dockerfile up to date with dependencies.

## Do NOT

- Do not modify generated files or lock files manually.
- Do not add dependencies without mentioning it.
- Do not change the project structure without asking first.
- Do not skip CI checks or disable linting rules.
- Do not commit files matching gitignore patterns.
```

## 支持的输出格式

| 格式 | 文件 | 使用者 |
|------|------|--------|
| `claude` | `CLAUDE.md` | Claude Code、Claude Desktop |
| `cursor` | `.cursorrules` | Cursor IDE |
| `copilot` | `.github/copilot-instructions.md` | GitHub Copilot |

## Python API

```python
from ruleforge import analyze_project, generate_rules
from ruleforge.generator import write_rules

# 分析项目
profile = analyze_project("./my-project")
print(profile.languages)    # {'Python': 42, 'TypeScript': 15}
print(profile.frameworks)   # ['FastAPI', 'React']

# 生成规则
rules = generate_rules(profile, formats=["claude", "cursor"])
for rule in rules:
    print(rule.filename, len(rule.content))

# 写入文件
write_rules(rules, "./my-project")
```

## 局限性

- 检测基于配置文件和文件扩展名，不做代码语义分析
- 生成的规则是一个不错的起点，但不是最终版本。建议根据项目的具体约定进行审查和定制
- 框架检测依赖于依赖声明（pyproject.toml、package.json 等）

## 参与贡献

欢迎贡献！特别是以下方面：

- 新增语言/框架检测（见 `analyzer.py`）
- 改进规则模板（见 `generator.py`）
- 支持更多 AI 助手格式

```bash
git clone https://github.com/he-yufeng/RuleForge.git
cd RuleForge
pip install -e ".[dev]"
pytest
```

## 许可证

MIT
