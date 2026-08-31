---
name: prismreel-git-publish
description: PrismReel GitHub publish workflow for safe commits, sensitive-data scans, and pushes to the GitHub repository.
---

# PrismReel GitHub Publish Workflow

Use this workflow when working in this repository and the user asks to publish work to GitHub, prepare a push, or follow the PrismReel release process.

## Core Rules

- Repository: `https://github.com/Zwens/prismreel.git`, remote name `origin`.
- Run sensitive-data checks before any push. Any hit must be resolved first.
- Commit messages must follow Conventional Commits.
- Use the local git configuration as the commit author. Do not switch identities.
- Day-to-day work commits and pushes directly to `main`. Open a `feature/*` branch only for changes that need isolation.

## Step 1: Confirm Remote and Branch

```bash
git remote -v
git branch --show-current
```

Expect `origin  https://github.com/Zwens/prismreel.git`.

## Step 2: Sensitive-Data Checks

Run all of the following checks. Any hit must be reviewed and resolved before continuing.

Search for suspicious hardcoded secrets:

```bash
git grep -E "['\"][a-zA-Z0-9_-]{40,}['\"]" -- ':(exclude)*.lock' ':(exclude)node_modules'
```

Search for internal company domains:

```bash
git grep -i "alibaba-inc.com"
```

Search for credential-like patterns:

```bash
git grep -iE "(sk-|AKID|access_key|password|pwd|token|bearer)" -- ':(exclude)*.lock' ':(exclude)*.example' ':(exclude)node_modules'
```

Search tracked sensitive files:

```bash
git ls-files | grep -E "\.env$|secret|credential|\.key$|\.pem$" | grep -v "\.example"
```

Review untracked files for `.env` backups or scratch notes before staging:

```bash
git status --porcelain | grep '^??'
```

## Step 3: Check .gitignore Coverage

Verify that `.gitignore` contains the expected sensitive and local paths:

```bash
grep -E "^\.env|^\.agent|^CLAUDE\.md|^output/" .gitignore
```

Expected coverage includes:

- `.env`
- `.agent/`
- `CLAUDE.md`
- `output/`

## Step 4: Optional Quality Checks

Run relevant checks when the changed files warrant them.

Backend formatting and lint:

```bash
black --check src/
flake8 src/
```

Frontend lint:

```bash
cd frontend && npm run lint
```

## Step 5: Stage Carefully

Stage only the intended files. Do not use `git add .`.

```bash
git add <specific-files>
```

## Step 6: Commit

Create an English Conventional Commit message:

```bash
git commit -m "feat: your descriptive commit message"
```

Common prefixes:

- `feat:`
- `fix:`
- `docs:`
- `style:`
- `refactor:`
- `test:`
- `chore:`

## Step 7: Push to GitHub

```bash
git push origin main
```

When working on a feature branch instead:

```bash
git push -u origin <branch-name>
```

## Step 8: Post-Push Verification

- Confirm the commit is visible at https://github.com/Zwens/prismreel
- Check README rendering if docs changed.
- Confirm no sensitive information leaked in the diff.

## Emergency Rollback

If the commit has not been pushed yet:

```bash
git reset --soft HEAD~1
```

If sensitive data was already pushed, clean history with BFG Repo-Cleaner and force push.
