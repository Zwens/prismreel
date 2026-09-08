---
name: lockfile-must-regenerate-in-build-env
description: 本機 npm 版本裝套件產生的 lockfile 可能跟 VPS Dockerfile build 用的 node:20-alpine 內建 npm 不相容
metadata:
  type: feedback
---

本機用 `npm install` 新增套件（如 opencc-js）後產生的 `package-lock.json`，直接 scp 到 VPS 拿去 `docker compose build` 可能導致 `npm ci` 失敗：`Missing: @swc/helpers@0.5.23 from lock file`。

**Why**：本機 npm 11.12.1（node 24）跟 `Dockerfile.frontend` 裡 `FROM node:20-alpine` 內建的 npm 10.8.2 版本落差較大，同一份 `package.json` 兩個 npm 版本解析出的 lockfile 內容細節不完全相同，`npm ci` 對 lockfile 一致性要求嚴格，版本不符會直接報錯拒絕安裝。

**How to apply**：
- 本機新增/更新 npm 依賴後，若要部署到用 `node:20-alpine`（或任何非本機版本）build 的環境，重新 build 前先在該版本容器內重新產生 lockfile：
  ```
  docker run --rm -v $(pwd)/frontend:/app -w /app node:20-alpine npm install --package-lock-only
  ```
- 這一步可以直接在 VPS 上做（VPS 已有 docker），不需要在本機额外裝 docker。
- 長遠可以考慮把本機開發環境的 node 版本鎖定跟 Dockerfile 一致（用 nvm/volta），減少這類版本落差重演，但目前規模小，遇到時現場修正即可，不必强制統一。
