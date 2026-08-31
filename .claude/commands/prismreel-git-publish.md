---
description: PrismReel GitHub 发布流程 - 安全提交、敏感数据扫描、推送到 GitHub 仓库
---

# PrismReel GitHub 发布流程

此 skill 整合了从本地开发到 GitHub 仓库的完整发布流程，包含安全检查和规范约束。

## 核心规则

- **仓库地址：`https://github.com/Zwens/prismreel.git`，remote 名称为 `origin`**
- **推送前必须执行敏感数据扫描** — 任何一项命中都必须修复后才能继续
- **Commit Message 遵循 Conventional Commits** (`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`)
- **提交作者使用本地 git 配置**，不需要切换身份
- 日常开发直接在 `main` 上提交并推送；只有需要隔离的大改动才另开 `feature/*` 分支

## 阶段一：提交前检查

### 1. 确认远程与分支

```bash
git remote -v
git branch --show-current
```

预期 remote 为 `origin  https://github.com/Zwens/prismreel.git`。

### 2. 敏感数据扫描

逐项执行，**任何一项命中都必须修复后才能继续**：

**搜索硬编码密钥（40+ 字符字符串）:**
```bash
git grep -E "['\"][a-zA-Z0-9_-]{40,}['\"]" -- ':(exclude)*.lock' ':(exclude)node_modules'
```

**搜索内部/公司域名:**
```bash
git grep -i "alibaba-inc.com"
```

**搜索 API Key 模式:**
```bash
git grep -iE "(sk-|AKID|access_key|password|pwd|token|bearer)" -- ':(exclude)*.lock' ':(exclude)*.example' ':(exclude)node_modules'
```

**检查敏感文件是否被追踪:**
```bash
git ls-files | grep -E "\.env$|secret|credential|\.key$|\.pem$" | grep -v "\.example"
```

**检查待暂存的未追踪文件里有没有 .env 备份 / 临时草稿:**
```bash
git status --porcelain | grep '^??'
```

### 3. 检查 .gitignore 完整性

```bash
grep -E "^\.env|^\.agent|^CLAUDE\.md|^output/" .gitignore
```

确保至少包含：`.env`、`.agent/`、`CLAUDE.md`、`output/`

## 阶段二：代码质量（可选但推荐）

**Python 代码格式化:**
```bash
black --check src/
flake8 src/
```

**前端 Lint:**
```bash
cd frontend && npm run lint
```

## 阶段三：提交与推送

### 1. 暂存文件

```bash
git add <specific-files>
```

**不要使用 `git add .`**，逐一确认文件。

### 2. 提交

```bash
git commit -m "feat: your descriptive commit message"
```

Commit 类型：
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式（不影响逻辑）
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具/依赖

### 3. 推送到 GitHub

```bash
git push origin main
```

如果是在 feature 分支上工作：

```bash
git push -u origin <branch-name>
```

## 阶段四：推送后验证

- 访问 https://github.com/Zwens/prismreel 确认内容正确
- 检查 README 格式渲染
- 确认无敏感信息泄露

## 紧急情况：撤销敏感信息

**未 push:**
```bash
git reset --soft HEAD~1
```

**已 push:**
需要使用 BFG Repo-Cleaner 清理历史并 force push。
