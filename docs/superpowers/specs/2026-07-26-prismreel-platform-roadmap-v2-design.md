# PrismReel Studio 短视频影视全流程平台 — 产品规划 v2.0

> **设计日期**: 2026-07-26
> **状态**: 待评审
> **取代**: `2026-07-26-prismreel-professional-studio-roadmap-design.md` (v1.1)
> **交付形态**: 内网服务器 Docker 共享部署，浏览器访问
> **使用场景**: 公司内部，无商业化维度

---

## 1. Context — 为什么重写 v1.1

v1.1 的三期路线图（后期工坊 → 音画大师 → 成片工厂）在**后期制作工具链**这一层设计扎实，但它回答的是「如何把 Assembly 步骤做成一个专业剪辑器」，而真实需求是「1-3 人如何持续批量产出 10-30 部短剧」。这两件事的优先级几乎相反。

### 1.1 核心矛盾的转变

v1.1 假设的用户行为是「精修一部片子」，实际用户行为是「无人值守跑完 30 部片子」。按 1 部剧 12 集 × 3 分钟 × 每集约 20 镜头估算：

```
1 人 10 部 = 2400 镜头        3 人 30 部 = 7200 镜头
每镜头 ≈ 2 张图 + 2 次视频抽卡
→ 约 14400 次视频生成 × 均 3 分钟 = 720 小时 API 时间
   串行 = 30 天    并发 10 路 = 3 天    并发 20 路 = 1.5 天
→ 7200 镜头 × 每镜头 ≥6 次人工交互 ≈ 4 万次点击   ← 真正的瓶颈
FFmpeg 合成 360 集 × 约 4 分钟 = 24 小时 CPU
存储 ≈ 150 GB（含废弃抽卡）
```

**结论**：吞吐由「并发度 × 无人值守时长 × 人工干预次数」决定，与剪辑器精细度无关。v1.1 把唯一契合此需求的「批量渲染队列」排在第 17-24 周，是最大的排序错误。

### 1.2 设计理念的转变

| | v1.1 | v2.0 |
|---|---|---|
| 理念 | 给人更强的手工工具 | **机器执行，人只做判断** |
| 核心 UX | 逐镜头精修 | 提交整部剧 → 无人值守跑完 → 只处理需决策的 5% |
| 优先级 | 剪辑 → 调色 → 批量 | **首个成片 → 地基 → 批量 → 增强 → 精修** |
| 缺失层 | 无平台层 | 补齐平台层（数据/任务/鉴权/成本/可观测） |

### 1.3 产品分层

```
创作层  剧本工作台 · 美术 · 选角 · 分镜
生成层  Provider 网关 · 抽卡 · 自动挑卡 · 一致性 · 资产库
后期层  粗剪 · 调色 · 音频 · 字幕
交付层  渲染工厂 · 质检 · 多平台导出 · 工程文件外链
平台层  账号权限 · 任务系统 · 数据层 · 存储GC · 成本归因 · 可观测 · 版本快照
        ↑ v1.1 完全缺失 —— 这是「成熟产品」与「功能集合」的分界线
```

---

## 2. 约束与前提

| 维度 | 决定 | 对设计的硬性影响 |
|---|---|---|
| 部署形态 | 内网服务器 Docker 共享，浏览器访问 | 需账号体系；需项目归属；docker-compose 新增 db + worker service |
| 团队规模 | 1-3 人，每人同时 10 部剧（10-30 部并发） | 协作/权限做到最小；**批量吞吐做到最大** |
| AI 算力 | **全部走云 API**，无本地模型推理 | 所有能力 = 外部调用 → 必须有统一网关：退避/限流/并发闸门/记账/结果归档 |
| 渲染算力 | **内网服务器 CPU 跑 FFmpeg** | 渲染是稀缺资源 → 代理预览、分片缓存、增量渲染、并发闸门均为必需项 |
| 客户端算力 | **浏览器不做重计算** | 砍掉 WebGL 实时 LUT；砍掉前端波形计算 → 均改服务端 |
| 数据库 | PostgreSQL | 见 §4.2 |
| 商业化 | 无 | 不做计费/配额强制，但**做成本归因与熔断**（防 bug 烧钱 + 内部核算） |
| 前端构建 | Next.js `output: 'export'` 静态导出 | **鉴权不能用 middleware**，只能客户端守卫 + axios interceptor |

---

## 3. 现状基线（已核实，带代码引用）

### 3.1 能用的部分（不要动）

- **端到端出片可用**：`pipeline.py:2798 merge_videos()` 是完整实现 —— concat + H.264/AAC 重编码 + dubbed 视频优先 + BGM mux。用户确认可产出完整短视频。
- **异步约定已审计**：`api.py:1-22` 有 2026-05-21 的审计注释，所有 handler 默认 `def` 走 anyio 线程池，事件循环不会被阻塞。
- **Provider 路由已抽象**：`src/utils/provider_registry.py` 按 model 名前缀路由到 family，catalog 驱动（`config/model_catalog/generated/model_catalog.json`，39 个 mode）。
- **素材已落盘**：`pipeline.py:3361 task.video_url = os.path.relpath(output_path, "output")`，不存在云端 URL 过期烂链问题。
- **路径安全已做**：`pipeline.py:38 _safe_resolve_path()` + `:31 _validate_safe_id()` 防目录穿越（但只覆盖 pipeline.py，见 §3.2）。
- **前端 Lightbox 基础设施优秀**：`shared/preview/LightboxProvider.tsx` 单例 Context + portal，可直接复用。
- **任务面板已有雏形**：`storyboard-r2v/shot-panel/TaskQueuePanel.tsx`(496行) 已有 Active/Done/Failed 三 tab + 跳转/取消/重试回调。

### 3.2 必须修的部分

| # | 问题 | 位置 | 严重性 |
|---|---|---|---|
| B1 | `_load_data` 解析失败**静默 `return {}`**，下次任何写操作用空 dict 覆盖全库 | `pipeline.py:395-397` | 🔴 静默全量数据丢失 |
| B2 | 三个 store 全部 `open(path,'w')` 直接覆写，无原子替换；写中途进程被杀 = 文件截断 | `pipeline.py:405, 3889, 3918` | 🔴 崩溃即丢库 |
| B3 | **121 处** save 调用点，每处全量 dump 整库 | `_save_data` 80 处 / `_save_series_data*` 27 处 / `_save_library_data*` 6 处 / `_save_after_asset_mutation` 9 处 | 🔴 批量生产下写放大灾难 |
| B4 | 轮询回调内触发整库 dump | `pipeline.py:3331` | 🔴 每个 provider task 中途都全量写盘 |
| B5 | 重启后 pending/processing **一律标记 failed**，`provider_task_id` 已存却无人使用 | `pipeline.py:127-172`, `models.py:216-218` | 🟠 长任务无法恢复，白烧 API 费用 |
| B6 | 失败兜底包装器 `api.py:2171` **从未注册**进 BackgroundTasks（两处 add_task 都直传 `pipeline.process_video_task`） | `api.py:2317, 2404` | 🟠 现存 bug，测试测不到 |
| B7 | 零并发闸门。`create_video_task` 对 batch_size 无上限，N 个 take = N 个 background task 齐发 | `api.py:2282-2317` | 🟠 触发限流 |
| B8 | wanx/kling/vidu 对 HTTP 429 **完全无感知**，当永久失败抛出；只有 MuleRouter 有退避 | `wanx.py:648,760,878` vs `mulerouter.py:249-268` | 🟠 |
| B9 | **零成本记账**。`LLMAdapter.chat` 丢弃 `usage`；`generate()` 返回的耗时被 `_` 丢掉 | `llm_adapter.py:71-145`, `pipeline.py:3271` | 🟠 |
| B10 | `resolve_provider_backend` 每次调用重新加载 214KB catalog，无缓存 | `provider_registry.py:250-251` | 🟡 批量下明显浪费 |
| B11 | `_safe_resolve_path` 只覆盖 pipeline.py；assets.py/storyboard.py/video.py/llm.py 用裸 `os.path.join("output", url)` | `assets.py:187,204,351` 等 | 🟡 安全不一致 |
| B12 | `_save_data` 用 pydantic v1 `.dict()`，另两个用 v2 `.model_dump()` | `pipeline.py:405` vs `:3889,3918` | 🟡 序列化行为不一致 |
| B13 | 静态挂载存在单复数历史包袱：`/files/outputs/videos`、`/files/videos` 都指向 `output/video` | `api.py:100-107` | 🟡 迁移时清理 |
| B14 | 列表接口无分页，`list_projects()` 返回全部项目完整对象树（含所有 frames/variants） | `api.py:435-437` | 🟠 项目一多即几十 MB |

### 3.3 死代码（可删）

`components/modules/Timeline.tsx`(77行，纯视觉 Mock，零引用)、`components/modules/PropertiesPanel.tsx`(902行，零引用)、`components/modules/AssetGrid.tsx`、`src/apps/comic_gen/export.py`(63行 Mock，真实路径走 `merge_videos`)。

---

## 4. 平台层架构设计

### 4.1 部署拓扑

```
┌─────────────────── 内网服务器 (Docker Compose) ────────────────────┐
│                                                                     │
│  frontend (nginx)   ──→  backend (FastAPI, N=1)                    │
│    静态导出产物            HTTP API + SSE                            │
│                              │                                      │
│                              ├──→ postgres  (元数据 / 任务 / 记账)   │
│                              │      + volume                        │
│                              │                                      │
│                              └──→ output volume (素材 / 成片)        │
│                                        ↑                            │
│  worker (FastAPI 同镜像, N=2~4)  ──────┘                            │
│    ├─ 生成 worker: 调云 API (I/O 密集, 高并发)                       │
│    └─ 渲染 worker: 跑 FFmpeg  (CPU 密集, 低并发 = CPU核数/2)         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ 出网
              DashScope / Kling / Vidu / MuleRouter / Freesound
```

**关键：生成 worker 与渲染 worker 分池**。生成是 I/O 等待（可 20 并发），渲染是 CPU 满载（只能 2-4 并发）。混在一个池里，渲染会饿死生成。

### 4.2 数据层：PostgreSQL 迁移

#### 迁移策略 — 三步走，不做大爆炸

**这是全项目风险最高的一块**（121 个调用点 + 8 个测试文件直接注入 store）。采用引入 Repository 抽象的渐进式迁移：

```
Step A (1.5w)  引入 Repository 接口，内部仍是现有 JSON 实现
               121 个调用点 → repo.save_script(id) / repo.save_series(id) / ...
               行为零变化，测试全绿。顺手修 B1/B2/B12（原子写 + 加载失败 fail-fast + 统一 model_dump）
Step B (2.5w)  实现 PostgresRepository（SQLAlchemy 2.0 + Alembic）
               同一接口双实现，配置项 STORAGE_BACKEND=json|postgres 切换
Step C (1w)    迁移脚本 output/*.json → PG；双跑校验；测试夹具改造；切换默认值
```

Step A 的价值：把「121 处散落的全量 dump」收敛成「一个接口的 N 个方法」，之后换实现只改一个文件。同时它独立可交付 —— 即使后续 PG 延期，B1/B2 这两个数据丢失路径也已经堵上。

#### Schema 设计要点

**顶层表**
```
users            (id, username, password_hash, role, display_name, created_at, is_active)
series           (id, title, description, workflow_mode, content_mode, owner_user_id, ...)
scripts          (id, series_id FK, episode_number, title, original_text, owner_user_id,
                  workflow_mode, merged_video_url, starred, version, created_at, updated_at)
```

**资产表 — 多态 owner（关键决策）**

`Character`/`Scene`/`Prop` 三个 Pydantic 类在 `Script`、`Series`、`GlobalAssetLibrary` 三处复用。**决定：一张表 + 多态 owner 列**，避免三套重复表：

```
characters  (id, owner_kind ENUM('script','series','library'), owner_id, name, ...,
             legacy_payload JSONB)     ← 7 个 [LEGACY] 字段收进 jsonb，不建列
scenes      (id, owner_kind, owner_id, ...)
props       (id, owner_kind, owner_id, ...)
  索引: (owner_kind, owner_id)
```

`GlobalAssetLibrary` 是无 id 单例 → 用 `owner_kind='library', owner_id='__global__'` 表示，不建表。

**变体池表 — 拆开 AssetUnit**
```
asset_units     (id, owner_kind, owner_id, slot, selected_image_id FK, selected_video_id FK,
                 image_prompt, video_prompt, created_at, updated_at)
                 slot ∈ reference_sheet | full_body | three_views | head_shot | image_asset | rendered_image
image_variants  (id, asset_unit_id FK, url, prompt, model, seed, created_at, ...)
video_variants  (id, asset_unit_id FK, url, prompt, model, duration, created_at, ...)
```

**分镜与关联**
```
storyboard_frames (id, script_id FK, position, scene_id FK, shot_type, camera_angle, duration,
                   selected_video_id FK, final_take_id FK, dubbed_video_task_id FK,
                   render_hash,                        ← 增量缓存用，见 §5.2
                   dialogue_structured JSONB, camera_movement JSONB, blocking JSONB,
                   audio_note JSONB, lighting JSONB, composition_data JSONB,
                   t2i_image_urls JSONB)               ← 有界 FIFO 数组，保持 jsonb
frame_characters  (frame_id FK, character_id FK)       ← 取代 List[str] 软外键
frame_props       (frame_id FK, prop_id FK)
```

**视频任务 — 单表 + 多态 owner**

`VideoTask` 现挂在 4 处（`Script.video_tasks`、`Character/Scene/Prop.video_assets`），但自带 `project_id`/`frame_id`/`asset_id` 三个软外键，天然适合单表：
```
video_tasks (id, project_id FK, frame_id FK NULL, asset_id NULL, owner_kind,
             status, error, model, prompt,
             provider_name, provider_task_id, provider_request_id,   ← B5 复活点
             provider_params JSONB,        ← Kling mode/sound/cfg_scale、Vidu audio 等稀疏列收进来
             reference_video_urls JSONB, reference_image_urls JSONB,
             created_at, started_at, finished_at)
```

**保留为 JSONB 的**：`ArtDirection.style_config` / `custom_styles` / `ai_recommendations`（本来就是 `Dict[str,Any]`）、`ModelSettings`、`PromptConfig`、`mix_settings`、frame 的 5 个结构化子对象、`composition_data`。理由：这些从不参与 WHERE 条件，建列只是增加 migration 负担。

**单一真相源决策**：`Series.episode_ids`(有序数组) 与 `Script.series_id`+`episode_number` 目前双向冗余且会不一致（`pipeline.py:409 _repair_series_bindings` 就是在修这个）。**决定：以 `scripts.series_id + scripts.episode_number` 为唯一真相源**，`episode_ids` 不入库，查询时 `ORDER BY episode_number`。`_repair_series_bindings` 降级为一次性迁移脚本，不再每次启动跑。

#### 必须同步改造的代码

| 现状 | 改造 |
|---|---|
| `pipeline.py:4026 _scan_library_asset_references()` 全表扫描查引用 | → `SELECT ... FROM frame_characters WHERE character_id=?` 索引查询 |
| `pipeline.py:127 _recover_orphan_tasks()` 启动全库扫描 | → 见 §4.3，改为 reattach 而非 fail-all |
| `api.py:435 list_projects()` 返回全部完整对象树 | → 分页 + 字段裁剪（列表页不 eager load frames/variants） |
| `pipeline.py:4370 find_custom_voice()` 双重循环 | → 单条索引查询 |
| `pipeline.py:4567 resolve_episode_assets()` 三层内存 merge | → 保留应用层 merge 语义，改为三次索引查询（优先级覆盖语义微妙，不要用 SQL 硬合） |
| `api.py` 13 处直接 `pipeline.scripts[id] = script` 绕过封装 | → 改走 repository；`delete_project`(`api.py:1393-1405`) 的非事务两步删除改为单事务 |
| 8 个测试文件直接注入 store | → 改用 repository fixture + 事务回滚（PG testcontainer 或 SQLite in-memory） |
| `scripts/migrate_assets_to_oss.py` 等 3 个脚本直读 projects.json | → 重写或标记弃用 |
| `HANDOFF.md:35-39` worktree 软链共享 output/*.json | → 改为共享 PG schema |

### 4.3 任务系统

#### 选型：PostgreSQL 表 + `SELECT FOR UPDATE SKIP LOCKED`，不引入 Celery/Redis

理由：1-3 人 / 30 部剧的规模下，PG 队列约 300 行代码即可满足，且少一个中间件容器、少一套运维、事务与业务数据天然一致。Celery 的价值在于跨语言/超大规模/复杂路由，此处均不需要。

#### 表设计

```sql
tasks (
  id, kind, status, priority,
  project_id, episode_id, shot_id, batch_job_id, owner_user_id,
  idempotency_key UNIQUE,          -- 幂等：同 key 重复提交直接返回既有任务
  payload JSONB, result JSONB, error TEXT,
  provider, provider_task_id,      -- 重启后 reattach 的钥匙
  attempt INT, max_attempts INT,
  lease_owner, lease_expires_at,   -- 租约：worker 心跳续租，过期自动回队
  cost_cents INT,
  created_at, started_at, finished_at
)
  kind   ∈ image | video | audio | subtitle | colorgrade | render | probe | score
  status ∈ queued | leased | running | succeeded | failed | canceled | reattaching
  索引: (status, priority DESC, created_at) / (lease_expires_at) WHERE status='leased'
```

#### Worker 主循环

```
1. 领取：UPDATE tasks SET status='leased', lease_owner=?, lease_expires_at=now()+90s
         WHERE id = (SELECT id FROM tasks WHERE status='queued'
                     AND provider_slot_available(provider)
                     ORDER BY priority DESC, created_at
                     FOR UPDATE SKIP LOCKED LIMIT 1)
         RETURNING *
2. 执行：心跳每 30s 续租；调 provider adapter
3. 收尾：succeeded / failed(可重试则 attempt+1 回 queued，指数退避 + 抖动)
4. 回收：单独的 reaper 协程扫 lease_expires_at < now() 的任务 → 回 queued
```

#### 三项关键能力

**a) 重启后 reattach（修 B5）** —— 现状是把 pending/processing 一律标 failed，理由写在 `pipeline.py:138-141`「可能已产生费用，重跑会双重扣费」。这个顾虑是对的，但**正确解法不是放弃，而是用已存的 `provider_task_id` 重新查云端状态**：

```
启动 / worker 接管时：
  status='running' 且 provider_task_id 非空 → status='reattaching'，提交一个轻量 probe 任务
    probe 查云端：完成 → 拉结果，标 succeeded（省下一次重跑的钱）
                  仍在跑 → 继续轮询
                  已失败/不存在 → 标 failed 待人工重试
  status='running' 且 provider_task_id 为空（尚未提交成功）→ 直接回 queued，安全重跑
```

**b) 并发闸门** —— 按 provider 分槽，配置化：
```yaml
# 保守默认值 —— 并发标定已决策推后（见 §8 R3），先求稳不求快
concurrency:
  dashscope_video: 4
  dashscope_image: 4
  kling: 4
  vidu: 4
  mulerouter: 4
  ffmpeg_render: 2        # = CPU 核数 / 2，渲染 worker 专用池
```
实现：`provider_slot_available()` 用一张 `provider_slots(provider, in_flight, max_slots)` 计数表在同一事务内 CAS，不需要 Redis。

**c) 幂等** —— `idempotency_key = sha256(kind + shot_id + render_hash)`。重复提交返回既有任务，是增量缓存（§5.2）的底座。

#### 统一入口

现有只有 3 个 entry point 需要挂到调度器：`pipeline.process_video_task`(`pipeline.py:3198`)、`process_asset_generation_task`(`pipeline.py:748`)、`process_motion_ref_task`。同步阻塞的重活端点（merge / export / generate_audio / dialogue_audio/batch / storyboard/render）全部改为提交任务并返回 task_id + SSE 订阅。

⚠️ 顺带修 B6：`api.py:2171` 那个从未被注册的包装器随本次改造删除，兜底逻辑内建到 worker 主循环。

### 4.4 鉴权与权限（最小可用）

**规模决定复杂度**：1-3 人，不做 RBAC、不做组织架构、不做 SSO。

**后端**
- `users` 表 + argon2 密码哈希（新增 `argon2-cffi`）
- JWT：**PyJWT 已在 `requirements.txt` 中**，直接复用。access token 8h，无 refresh（内部使用，过期重登即可）
- 角色两个：`admin`（可见全部项目 + 用户管理 + 成本看板全局视图）/ `member`（自己的项目 + 自己的成本）
- 项目归属：`scripts.owner_user_id` / `series.owner_user_id`；`member` 只能读写自己的，不做共享编辑（1-3 人场景下共享编辑的收益低于并发冲突的成本）
- 依赖注入：`Depends(get_current_user)`，白名单放行 `/health`、`/auth/login`、`/files/*`（静态素材不鉴权，内网可接受）

**前端（受静态导出约束）**
- 新增 `store/authStore.ts`（persist 到 localStorage）
- **一处全局 interceptor 覆盖 150+ 处裸 axios 调用**（它们共用默认实例）：
  ```ts
  axios.interceptors.request.use(c => { c.headers.Authorization = `Bearer ${token}`; return c })
  axios.interceptors.response.use(null, e => { if (e.response?.status===401) gotoLogin(); throw e })
  ```
- fetch 调用点（`api.ts` 里语音/音频/合成类 + `projectStore.ts:513`）需单独包一层 `authFetch`
- hash router 守卫：`page.tsx` 的路由分支前置 `if (!token && hash !== '#/login') → '#/login'`
- 新增 `#/login` 页

**乐观并发**：`scripts.version` 整数列，更新时 `WHERE version = ?`，冲突返回 409 + 前端提示刷新。取代当前"后写覆盖先写"。

### 4.5 成本归因与熔断

不做计费，做**可见性 + 防失控**。

**a) catalog 加价格** —— `model-catalog.schema.json` 是宽松 stub，加字段无阻力。在 `modes[*]` 增加：
```json
"pricing": { "unit": "per_second|per_image|per_1k_tokens", "price_cents": 40, "currency": "CNY", "updated_at": "2026-07-26" }
```

**b) 记账表**
```sql
usage_events (id, task_id FK, project_id, episode_id, user_id,
              provider, model, unit, quantity, unit_price_cents, cost_cents,
              created_at)
```

**c) 埋点位置**（现成锚点）
- `wanx.py:895 on_provider_ids` 回调 —— 任务创建成功即刻触发，是天然的「一次计费事件」主键
- `LLMAdapter.chat`(`llm_adapter.py:71-145`) **停止丢弃 `usage`**，返回 `(content, usage)`
- `VideoGenModel.generate()` 返回的 `duration_seconds` 现被 `_` 丢掉（`pipeline.py:3271` 等），改为记录

**d) 熔断** —— `projects.budget_cents` + `series.budget_cents`，入队前校验累计 `cost_cents`，超限拒绝入队并置 batch_job 为 `paused_over_budget`。**这不是商业化，是防一个死循环 bug 烧掉几千块。**

### 4.6 Provider 网关统一

把 `mulerouter.py:249-268 _request_with_retry` 提取为 `src/utils/http_retry.py` 公共模块，四家共用：
- 429/502/503/504/ConnectionError → 指数退避 + 抖动，`min(2^n × 5, 60)s`，最多 3 次（修 B8）
- 修 B10：`get_default_provider_registry()` 加 `@lru_cache`，catalog 只加载一次
- 修 B11：`assets.py` / `storyboard.py` / `video.py` / `llm.py` 的裸 `os.path.join("output", url)` 统一走 `_safe_resolve_path`（提取到 `src/utils/paths.py`）

### 4.7 存储与 GC

150GB 量级需要生命周期管理：
- 目录规范化：清理 B13 的单复数包袱，统一 `output/{kind}/{project_id}/{...}`，旧 URL 在 PG 迁移时一次性重写
- GC 策略：抽卡产生的**未被任何 `selected_*_id` 引用**且超过 N 天的 variant 文件 → 标记 → 宽限期 → 删除。dry-run 优先，`GET /admin/gc/preview`
- 中间产物（`merge_list_*.txt`、proxy 代理片、单帧预览缓存）随任务结束即删

### 4.8 可观测

- 结构化日志：每条带 `task_id` / `project_id` / `user_id` / `provider`
- `GET /admin/metrics`：任务队列深度、各 provider in-flight/成功率/P50-P95 耗时、24h 成本、存储占用
- 任务详情页可查看完整执行轨迹（每次 attempt 的时间/错误/provider_task_id）

---

## 5. 分期路线图

```
V-1 首个成片    V0 地基         V1 批量流水线    V2 后期增强     V3 能好看      V4 量产闭环
   4 周          6.5 周            6 周            4 周           4 周           5 周
┌──────────┐  ┌──────────┐   ┌──────────────┐ ┌───────────┐  ┌───────────┐  ┌───────────┐
│数据安全  │  │Repository│   │Provider 网关  │ │RenderEngine│ │调色增强    │  │质量自检    │
│BGM 素材  │  │PG 迁移   │   │成本记账       │ │粗剪        │ │色彩锚点    │  │多平台导出  │
│渲染管线v1│  │任务系统  │   │批量编排 DAG   │ │工程文件导出│ │剧本工作台  │  │成本看板    │
│音频闪避  │  │账号鉴权  │   │增量缓存       │ │字幕增强    │ │模板系统    │  │版本快照    │
│字幕系统  │  │分页改造  │   │自动挑卡       │ │           │  │           │  │转场库      │
│端到端验证│  │部署编排  │   │批量看板       │ │           │  │           │  │           │
└──────────┘  └──────────┘   └──────────────┘ └───────────┘  └───────────┘  └───────────┘
     ↑
  先用一部剧验证端到端价值，再投入规模化基础设施

总计 29.5 周 ≈ 6.8 个月
```

**每期独立可交付、可上线、可停在任意一期。**

---

### V-1「首个完整成片」— 4 周

**目标**：**用一部剧走通全流程，产出一个可直接发布的成片**。在投入 6.5 周地基之前，先验证端到端价值链是否成立。

**为什么排在最前**：现有管线已能出片（`pipeline.py:2798 merge_videos` 是完整实现），距离「可发布」只差字幕和声音两件事。先补齐它们拿到一个真实成品，比先做 6.5 周看不见的地基更能验证方向、也更能暴露真实卡点 —— 后续 V0/V1 的排期可以据此修正。

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| -1.1 | 数据安全急救 | 0.5 | 修 B1（`pipeline.py:395` 加载失败 fail-fast，不再静默 `return {}` 后被空 dict 覆盖）、B2（临时文件 + `os.replace` 原子写 + 滚动 10 份备份）、B12（统一 `model_dump()`）。**本阶段正在跑真实项目，丢数据代价最高，必须先堵** |
| -1.2 | BGM 素材落地 | 0.2 | `audio.py:23-32` 的 8 个预设 catalog 已定义、`pipeline.py:2991 _maybe_apply_bgm_mux` 已实现，但 `output/presets/bgm/` 目录**不存在**，导致 `:3009-3011` 静默跳过 → 导出静音。落地 8 个 CC0 音频文件 + 启动时校验缺失并告警 + 随部署包发布。**零代码改动** |
| -1.3 | 渲染管线 v1 | 1.0 | 把 `merge_videos` 从纯 concat 升级为可挂滤镜链的 `RenderEngine` 雏形：`per-shot 预处理 → concat → 音频链 → 字幕烧录 → encode`。保留现有 `merge_videos` 签名与行为作为降级路径。这是字幕和音频落地的前置 |
| -1.4 | 音频完善 | 0.5 | 现有 `amix` 之上补 `sidechaincompress`（BGM 自动闪避人声）+ `loudnorm`（整片电平归一，目标 -16 LUFS）。批量场景下音量忽大忽小无人逐集修，必须自动化 |
| -1.5 | 字幕系统 v1 | 1.5 | **不用 ASR**：台词在 `frame.dialogue`、时间码在 TTS 产物与 `DialogueAudioRow` 的 `offset_ms` 里，直接生成 ASS 比 ASR 准确且零成本。含 2 套样式模板（抖音风 / 影视风）+ 烧录 + 表格式时间码微调入口 |
| -1.6 | 端到端验证与修坑 | 0.3 | 完整跑一部 12 集剧，记录每步耗时、失败率、人工干预次数，产出**基线报告**用于修正 V0/V1 排期 |

**范围取舍（明确不做）**
- **调色不在本期**。「可发布」定义为技术完整（有字幕、有声音、音量正常），不含「更好看」。调色放 V3。
  ⚠️ 若实测发现分镜色调跳变严重到影响发布，可把「6 预设全局静态 LUT」加进本期，代价 **+1 周**。这个判断留给 -1.6 的基线报告。
- 不做粗剪、不做工程文件导出、不做批量、不做地基、不做鉴权。

**验收**
- 一部 12 集短剧，每集产出带烧录字幕、BGM 混音正常、电平归一的 MP4，**可直接上传抖音/视频号**
- `ffprobe` 确认音轨存在；`volumedetect` 峰值 < -1dB 无爆音；整片 LUFS 在 -16±1
- 强制中断后端进程再重启，`projects.json` 完好、可正常加载（验证 -1.1）
- 产出基线报告：一集从剧本到成片的实际耗时、API 调用次数、人工点击次数、失败率

---

### V0「地基」— 6.5 周

**目标**：把数据层、任务层、账号层做实。无用户可见新功能，但后面各期全部依赖它。**排期与内容应按 V-1 的基线报告复评后再启动。**

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| ~~0.1~~ | ~~数据安全急救~~ | — | **已移至 V-1.1** |
| 0.2 | Repository 抽象 | 1.5 | 定义接口；121 个调用点迁移；JSON 实现保持行为不变；测试全绿 |
| 0.3 | PG schema + ORM | 2 | SQLAlchemy 2.0 + Alembic；§4.2 全部表；`PostgresRepository` 实现 |
| 0.4 | 迁移与切换 | 1 | `scripts/migrate_json_to_pg.py`；双跑校验；测试夹具改造；`STORAGE_BACKEND` 切默认 |
| 0.5 | 任务系统 | 1.5 | tasks 表 + worker 进程 + 租约 + reaper + reattach(修 B5) + 并发闸门(修 B7) + 幂等；3 个 entry point 接入；修 B6 |
| 0.6 | 账号鉴权 | 0.5 | users 表 + JWT + 前端 interceptor + 登录页 + 路由守卫 + 乐观锁 |
| 0.7 | 分页改造 | 0.5 | 修 B14；`list_projects`/`list_series`/`list_library_assets` 加分页与字段裁剪 |
| 0.8 | docker-compose | 0.25 | 新增 postgres service + volume；新增 worker service（生成池 / 渲染池分开）；健康检查 |

> 明细合计 7.25 人周。0.6 鉴权 / 0.7 分页 / 0.8 部署 三项与 DB 主线（0.2-0.4）无依赖，可并行，故排期取 **6.5 周**。若单人开发则按 7.5 周计。

**验收**
- 20 个项目并发跑，无数据丢失、无写放大卡顿
- 强杀 worker 容器，任务在 90s 内自动回队并继续，已提交云端的任务 reattach 成功而非重跑
- 多用户登录，member 看不到他人项目
- `output/*.json` 完整迁入 PG，逐字段 diff 校验通过
- 现有全部测试通过

---

### V1「批量流水线」— 6 周

**目标**：一个人提交 10 部剧后可以下班，回来只处理需要决策的部分。**这是全项目的核心价值所在。**

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| 1.1 | Provider 网关统一 | 1 | §4.6：退避提取公共模块、catalog 缓存、路径安全统一 |
| 1.2 | 成本记账 | 1 | §4.5：catalog pricing、usage_events、三处埋点、预算熔断 |
| 1.3 | 批量编排 DAG | 1.5 | `batch_jobs` 表 + `BatchOrchestrator`。Series 级提交，DAG：`分镜 → (每镜头: 生图 → 生视频) → 配音 → 字幕 → 调色 → 合并`。节点失败不阻塞同级其他节点 |
| 1.4 | 增量缓存 | 0.5 | `frames.render_hash = sha256(prompt + refs + model + params + style)`。hash 未变且产物存在 → 跳过。改一句提示词只重跑一个镜头 |
| 1.5 | 自动挑卡 | 1 | 复用 `src/models/qwen_vl.py QwenVLModel`。对同一镜头的 N 个候选按「构图/一致性/伪影」评分，自动选优。三档模式：`全自动` / `自动+标记存疑` / `全手动`。**这条直接砍掉约一半的人工点击量** |
| 1.6 | 批量看板 | 1 | 改造 `TaskQueuePanel.tsx`(496行) 为顶级页 `#/renders`。Series/Episode/Shot 三级树、失败清单、一键重试全部失败、暂停/恢复/取消。SSE 实时进度 —— 把 `api.ts:1094 refineBatchFrames` 的手写 SSE 读流抽成通用 `streamSSE()` 复用 |

**验收**
- 提交 1 部 12 集剧，无人值守跑完全流程，产出 12 个成片
- 中途改 1 个镜头提示词重跑，只有该镜头重新生成
- 人为制造 20% 失败，失败清单准确，一键重试后补齐
- 成本报表按 项目/集/人 三个维度可查，与实际账单误差 < 10%
- 触发预算上限时任务暂停而非继续烧钱

---

### V2「后期增强」— 4 周

**目标**：在 V-1 已能出可发布成片的基础上，补齐编辑能力与专业工具退路。

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| 2.1 | RenderEngine 完全体 | 1.5 | 把 V-1.3 的雏形升级为非破坏性 EDL → 单趟 `filter_complex`：per-shot(trim+speed+crop+lut3d+eq) → xfade → concat → 音频链 → subtitles → encode。删除 Mock `export.py`。**代理预览**：480p 低码率分片缓存，预览永不重渲染 |
| 2.2 | 粗剪 | 1.5 | 新建组件（**丢弃 `Timeline.tsx` Mock**）。单视频轨 + 音频轨 + 字幕轨的**简化时间轴**：拖拽排序、trim 入出点、时长调整、删除、替换。不做逐帧步进、不做多轨嵌套、不做前端波形计算（波形 peaks 由服务端预生成 JSON）。需新增拖拽库（`dnd-kit`） |
| 2.3 | 工程文件导出 | 0.5 | **不逆向剪映草稿格式**（未公开、版本脆弱）。用 OpenTimelineIO 作为内部表示，导出 **FCPXML**（剪映/达芬奇/Premiere 均可导入）+ **EDL**。半天工作量换来「精剪交给专业工具」的完整退路 |
| 2.4 | 字幕增强 | 0.5 | 在 V-1.5 两套模板基础上：第 3 套综艺风模板、双语字幕（LLM 翻译 + 人工校对）、ASR(Paraformer) 作为导入外部音频的兜底路径 |

**验收**
- 预览响应 < 2s（走代理缓存，不重渲染）
- 导出的 FCPXML 在达芬奇中正确打开，分镜、时间码、音轨对齐
- 粗剪删除一个镜头后重新导出，字幕时间码自动重排正确

---

### V3「能好看」— 4 周

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| 3.1 | 调色 | 1 | **8 个精选预设**（非 19）：电影感 / 古风 / 仙侠 / 都市 / 悬疑 / 日系 / 港风 / 暗黑。静态 `.cube` LUT + `eq/colorbalance/unsharp/vignette` 手动参数 + 逐 shot override。**实时预览用服务端单帧渲染**（提首帧 → 应用滤镜 → 返回 JPEG，< 100ms），不用 WebGL —— 客户端不做重计算，且效果与最终渲染完全一致。参考作品名仅存于内部调参文档，**不在 UI 展示**（商标风险）<br>⚠️ 若 V-1 已提前落地 6 预设全局调色，本项缩减为 0.5 周 |
| 3.2 | 上游色彩锚点 | 0.5 | 分镜色调不一致的根因在生成端。在 Art Direction 增加色彩锚点（主色/色温/对比基线），注入生成提示词与参考图选择。**治本，且比后期 LUT 便宜** |
| 3.3 | 剧本工作台 | 2 | 扩展 `ScriptProcessor.tsx`(356行，最小的活跃主步)。四项能力：<br>① **集数节奏表** — 每集时长/钩子/反转点/结尾悬念的结构化编辑<br>② **人物小传与关系图** — 从已有 Character 派生，补性格/动机/关系<br>③ **跨集一致性校验** — LLM 检查人物性格矛盾、道具穿帮、时间线错乱，输出问题清单<br>④ **钩子辅助** — 复用已有的 `last_episode_summary_cache` / `next_hook_cache`（`models.py:576-596` 已存在，说明这个方向已有基础） |
| 3.4 | 模板系统 | 0.5 | 从已跑通的项目提取配置快照（风格/模型/提示词/音频/字幕样式/调色/导出预设）。**批量生产下这是省时最多的功能**：第 1 部剧调好，后 9 部直接继承 |

---

### V4「量产闭环」— 5 周

| # | 工作项 | 周 | 说明 |
|---|---|---|---|
| 4.1 | 质量自检 | 1.5 | 导出后自动扫描，**只把异常推给人**。技术项：FFprobe 分辨率一致性、`volumedetect` 爆音、OpenCV `compareHist` 色调跳变、字幕阅读速度(3-8字/秒)、镜头时长 95 分位异常。可自动修复项一键修 |
| 4.2 | 多平台导出 | 1 | 抖音/快手/B站/YouTube 预设：scale+pad/crop + 安全边距（避开平台 UI 遮挡）+ 封面图（首帧 + drawtext 标题） |
| 4.3 | 成本看板 | 1 | 独立顶级页 `#/cost`（**不要塞进已 1150 行的 SettingsPage**）。按 项目/集/人/模型/时间 维度。前端无图表库 → 手写 SVG 柱状/折线，不引重依赖 |
| 4.4 | 版本快照 | 1 | 建立在 PG 之上（`snapshots` 表 + JSONB payload），只存配置引用不复制视频。自动（创建/每5次变更/每小时/里程碑）+ 手动标签。保留 20 份 FIFO |
| 4.5 | 转场库 | 0.5 | `xfade` 6 种：硬切/淡入淡出/黑场/白场/推入/擦除。批量场景下更多转场无实用价值 |

---

## 6. 关键技术决策记录

| # | 决策 | 备选 | 理由 |
|---|---|---|---|
| D1 | PG 表 + `SKIP LOCKED` 做队列 | Celery + Redis / RQ / Arq | 1-3 人规模下约 300 行代码即可；少一个中间件容器；任务状态与业务数据同事务，不会出现「任务成功但数据没提交」 |
| D2 | Repository 抽象后再迁 PG | 直接大爆炸迁移 | 121 个调用点 + 8 个测试文件直接注入 store。渐进式让每一步都可回滚，且 Step A 单独就修掉两个数据丢失路径 |
| D3 | 资产表用多态 owner 列 | 三套重复表 / 单一 assets 表 | `Character/Scene/Prop` 在 3 处复用同一 Pydantic 类。多态列避免 9 张近似表，同时保留三种资产各自的字段差异 |
| D4 | 重启 reattach 而非 fail-all | 保持现状 / 无条件重跑 | `provider_task_id` 已存但闲置。reattach 省下重跑费用，同时避免无条件重跑的双重扣费 —— 原注释的顾虑用 probe 查询解决，而不是放弃恢复 |
| D5 | 字幕从剧本+TTS时间码生成 | ASR (Paraformer) | 台词是我们自己写的、音频是我们自己合成的，时间码精确已知。ASR 只会引入识别错误，且要花钱。ASR 降级为导入外部音频的兜底 |
| D6 | 服务端单帧预览调色 | WebGL LUT 实时预览 | 约束明确「客户端不做重计算」；单帧 FFmpeg < 100ms 完全够用；且与最终渲染用同一套滤镜，所见即所得，无色彩管理偏差 |
| D7 | OTIO → FCPXML/EDL | 逆向剪映 draft_content.json | 剪映草稿格式未公开、随版本变化易碎。FCPXML 是开放标准，剪映/达芬奇/Premiere 均可导入，且有成熟 Python 库 |
| D8 | 调色 8 预设而非 19 | 保留 v1.1 的 19 个 | 批量生产下模板级统一调色即可，逐剧精细分品类的收益低于维护 19 套 LUT + 关键帧机制的成本。动态关键帧（穿越/大反转）降为 P2 |
| D9 | 生成池与渲染池分开 | 单一 worker 池 | 生成是 I/O 等待（可 20 并发），渲染是 CPU 满载（只能 2-4）。混池会让渲染饿死生成 |
| D10 | 最小权限模型（owner + 2 角色） | RBAC / 共享编辑 | 1-3 人。共享编辑的并发冲突成本高于其收益 |
| D11 | 参考作品名不进 UI | v1.1 在预设卡片展示《苍兰诀》等 | 商标与暗示关联风险。内部调参文档保留 |

---

## 7. 技术架构影响

### 7.1 新增后端模块

```
src/
├── db/
│   ├── models.py           # V0: SQLAlchemy ORM 模型
│   ├── repository.py       # V0: Repository 接口
│   ├── json_repo.py        # V0: 现有 JSON 实现（迁移期）
│   ├── pg_repo.py          # V0: PostgreSQL 实现
│   └── migrations/         # V0: Alembic
├── tasks/
│   ├── queue.py            # V0: 入队/领取/租约/幂等
│   ├── worker.py           # V0: worker 主循环 + reaper
│   ├── reattach.py         # V0: 重启后云端任务恢复
│   └── gates.py            # V0: provider 并发闸门
├── auth/
│   ├── models.py           # V0: users
│   ├── jwt.py              # V0: 复用已有 PyJWT
│   └── deps.py             # V0: FastAPI 依赖注入
├── billing/
│   ├── pricing.py          # V1: catalog 价格解析
│   ├── ledger.py           # V1: usage_events 记账
│   └── budget.py           # V1: 熔断
├── utils/
│   ├── http_retry.py       # V1: 从 mulerouter 提取的公共退避
│   └── paths.py            # V1: 统一 _safe_resolve_path
└── apps/comic_gen/
    ├── editing.py          # V-1: RenderEngine 雏形 → V2 完全体（取代 export.py）
    ├── audio_mixer.py      # V-1: ducking + loudnorm，取代 Mock AudioGenerator
    ├── subtitle.py         # V-1: 剧本+时间码 → ASS → 烧录（V2 增强双语/ASR兜底）
    ├── batch.py            # V1: BatchOrchestrator (DAG)
    ├── autopick.py         # V1: QWEN-VL 候选评分
    ├── otio_export.py      # V2: OTIO → FCPXML/EDL
    ├── color_grade.py      # V3: LUT + 单帧预览
    ├── screenplay.py       # V3: 剧本工作台（节奏/小传/一致性校验）
    ├── template.py         # V3: 模板 CRUD
    ├── quality.py          # V4: 质检 Pipeline
    └── snapshot.py         # V4: 版本快照
```

**删除**：`src/apps/comic_gen/export.py`（Mock 死路径）

### 7.2 新增前端

```
frontend/src/
├── store/authStore.ts                    # V0
├── lib/http.ts                           # V0: axios 全局 interceptor + authFetch
├── lib/router.ts                         # V0: 从 page.tsx(1074行) 抽出 hash router
├── lib/sse.ts                            # V1: 从 api.ts:1094 抽出通用 streamSSE
├── app/                                  # 仍是单路由 + hash（静态导出约束）
└── components/
    ├── auth/LoginPage.tsx                # V0
    ├── renders/BatchDashboard.tsx        # V1: 改造 TaskQueuePanel.tsx
    ├── assembly/SubtitleEditor.tsx       # V2
    ├── assembly/RoughCutTimeline.tsx     # V2: 新建，废弃 Timeline.tsx
    ├── assembly/AudioMixer.tsx           # V2
    ├── assembly/ColorGradePanel.tsx      # V3
    ├── screenplay/ScreenplayWorkbench.tsx # V3
    ├── cost/CostDashboard.tsx            # V4: 独立页，不进 SettingsPage
    └── quality/QualityReport.tsx         # V4
```

**新增依赖**：`dnd-kit`（粗剪拖拽，V2）。图表手写 SVG，不引库。

**必须遵守的既有约定**：
- 语义 token 配色（`bg-surface` / `text-text-secondary` 等），有 `npm run check:colors` 校验
- 全部文案走 `useTranslations`，`messages/zh.json` + `en.json` 同步更新
- 不往 `StoryboardR2V.tsx`(2300行) / `ArtDirection.tsx`(1204行) / `SettingsPage.tsx`(1150行) 里加新功能

### 7.3 新增基础设施

```yaml
# docker-compose.yml 新增
postgres:   image: postgres:16, volume: pgdata
worker-gen:      # 生成池，replicas 由 provider 并发上限决定
worker-render:   # 渲染池，replicas = CPU 核数 / 2
```

### 7.4 外部依赖

| 能力 | 用途 | 期 | 备注 |
|---|---|---|---|
| PostgreSQL 16 | 元数据/任务/记账 | V0 | 容器内，随部署 |
| SQLAlchemy 2.0 + Alembic | ORM + 迁移 | V0 | 新增 |
| argon2-cffi | 密码哈希 | V0 | 新增（PyJWT 已有） |
| FFmpeg | 全部视频音频处理 | 全期 | 已集成，扩展滤镜链 |
| OpenTimelineIO | 工程文件导出 | V2 | 新增 |
| colour-science | LUT 生成（一次性离线，产物内置） | V3 | 仅开发期 |
| QWEN-VL | 自动挑卡 / 伪影检测 | V1/V4 | 已有 `src/models/qwen_vl.py` |
| DashScope Paraformer | ASR 兜底（非主路径） | V2 | 免费额度 |
| OpenCV | 色调跳变检测 | V4 | 新增 |
| Freesound / Pixabay Music | SFX / BGM 素材 | V3 | ⚠️ 商用授权条款需逐条核实 |

---

## 8. 风险与缓解

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **PG 迁移打掉全部测试夹具** — 8 个测试文件直接 `p.scripts = {...}` | V0 延期 | D2 的 Repository 抽象先行；测试改用 repository fixture；预留 1 周专门做夹具改造（已计入 0.4） |
| R2 | **资产三层解析语义微妙** — `resolve_episode_assets` 是优先级覆盖不是 join，且返回活对象引用（别名语义，`pipeline.py:4100` 注释） | 数据错乱 | 保留应用层 merge，只把三次查找改为索引查询；ORM 用 `expire_on_commit=False` 保持 identity map；为这块单独写对照测试 |
| R3 | **各家云 API 并发上限未知** — 全仓库和三篇厂商文档均无 QPS/并发数记录 | 批量触发限流 | **并发标定推后**（已决策）。V1 的闸门取保守默认值（各 provider 4 路），配置化可随时上调；配合 R8 的退避机制吸收偶发 429。待 V1 上线后出现真实吞吐压力时，再做阶梯标定实验把实测值写进配置 |
| R4 | **CPU 编码是吞吐瓶颈** — 360 集 × 4 分钟 = 24h | 渲染排队 | 渲染池独立；代理预览不走完整渲染；增量缓存跳过未变更；`-preset veryfast` + 只在终稿用高质量档 |
| R5 | 存储 150GB+ 无上限增长 | 磁盘打满 | V0 起就记录 variant 引用关系；GC 在 V4 落地但 dry-run 报告 V1 就提供 |
| R6 | 剧本工作台范围易失控 | V3 延期 | 严格限定四项能力（§5 V3.3），不做富文本编辑器、不做协同编辑、不做剧本版本对比 |
| R7 | 自动挑卡误判导致批量产出质量下降 | 返工 | 三档模式，默认「自动+标记存疑」；评分结果与人工选择做对照统计，达标后再允许全自动 |
| R8 | 素材库商用授权 | 合规 | V3 前核实 Freesound/Pixabay 条款；优先选 CC0；建立内部素材白名单 |
| R9 | 静态导出限制导致鉴权绕过 | 安全 | 前端守卫只是 UX，**所有鉴权在后端 `Depends` 强制**；`/files/*` 内网不鉴权是有意识的取舍，需在部署文档中写明「服务器不得暴露公网」 |
| R10 | 29.5 周周期内需求变化 | 计划失效 | 每期独立可交付、可停；每期结束做一次优先级复评 |

---

## 9. 验证方法

### V-1
```bash
# 数据安全（先做，因为本期在跑真实项目）
kill -9 <backend-pid>   # 在密集写入时强杀
# → 重启后 projects.json 完好可加载；备份目录有 10 份滚动快照
# → 手动损坏 projects.json 后启动 → fail-fast 报错退出，绝不用空 dict 覆盖

# BGM 落地
ls output/presets/bgm/*.mp3 | wc -l        # = 8
# 启动日志：无 "preset file missing" 告警

# 完整成片
提交一部 12 集剧 → 逐集导出
ffprobe -show_streams out.mp4 | grep audio  # 音轨存在
ffmpeg -i out.mp4 -af volumedetect -f null -   # max_volume < -1dB
ffmpeg -i out.mp4 -af loudnorm=print_format=json -f null -   # input_i ≈ -16 LUFS
# 肉眼确认：字幕烧录清晰、位置正确、BGM 在人声处自动压低

# 基线报告（用于修正 V0/V1 排期）
一集实际耗时 / API 调用次数 / 人工点击次数 / 各步失败率
```

### V0
```bash
# 数据迁移一致性
python scripts/migrate_json_to_pg.py --dry-run --diff   # 逐字段 diff，零差异
pytest tests/ -v                                        # 现有测试全绿

# 任务恢复
docker compose kill worker-gen                          # 强杀
# → 90s 内任务回队；已提交云端的走 reattach，日志出现 "reattached, cost saved"

# 并发写
python scripts/bench_concurrent_writes.py --projects 20 --ops 500
# → 无数据丢失，P95 写延迟 < 50ms（对比 JSON 全量 dump 的秒级）

# 鉴权
curl -X GET .../projects                                # 401
curl -H "Authorization: Bearer <member-token>" .../projects   # 只返回自己的
```

### V1
```bash
# 端到端批量
POST /series/{id}/batch_render  {episodes: [1..12]}
# → 无人值守跑完，12 个成片；批量看板全程可见进度

# 增量缓存
PATCH /frames/{id}  {prompt: "..."}  &&  重新提交批量
# → 日志显示 skipped=N-1, rendered=1

# 成本准确性
GET /projects/{id}/usage    # 与云厂商账单对比，误差 < 10%

# 熔断
设 budget_cents=100 后提交大批量 → batch_job 状态变 paused_over_budget，无新任务入队
```

### V2
```bash
# 完整成片
提交剧本 → 批量跑 → 导出
# → MP4 带烧录字幕、混音正常（ffprobe 检查音轨）、无爆音（volumedetect max < -1dB）

# 预览性能
点击任意 shot 预览 → 首帧 < 2s（走代理缓存）

# 工程文件
导出 FCPXML → 在达芬奇打开 → 分镜数量/时间码/音轨与平台内一致
```

### V3 / V4
```bash
# 调色一致性
应用预设后 → 逐 shot 直方图相似度 > 0.85（OpenCV compareHist）

# 单帧预览延迟
POST /projects/{id}/frames/{fid}/color_preview → < 100ms

# 剧本一致性校验
故意植入人物性格矛盾 + 道具穿帮 → 校验器准确报出

# 质检
植入分辨率不一致 / 爆音 / 字幕超速 → 质检报告全部命中
```

---

## 10. 与 v1.1 的差异总表

| 模块 | v1.1 | v2.0 | 变更理由 |
|---|---|---|---|
| 首个完整成片 | 无此概念 | **V-1 第 1-4 周** | 先用一部剧验证端到端价值，再投规模化基础设施；产出基线报告修正后续排期 |
| 平台层 | 无 | V0 全新 6.5 周 | 「成熟产品」与「功能集合」的分界线 |
| 批量渲染 | V3 第 17-24 周 | **V1 第 11-17 周** | 1-3 人做 30 部剧，这是唯一核心需求 |
| 并发标定 | 无 | 推后到有真实吞吐压力时 | 先跑通一个完整流程是重点；闸门取保守默认值 + 退避兜底 |
| 专业多轨时间轴 | V1 核心，8 周 | 降级为「粗剪」1.5 周 + 工程文件导出 0.5 周 | 7200 镜头没人有时间逐个精修；精剪交给剪映/达芬奇 |
| 字幕 | V2 第 9-16 周 | **V-1 第 1-4 周**，且改为不用 ASR | v1.1 自己写「短剧必须带字幕才能发布」却排在中段；台词和时间码本来就在库里，不需要 ASR |
| BGM 导出静音 | 未识别 | V-1.2 修复（放 8 个文件，零代码） | `_maybe_apply_bgm_mux` 已实现，只是 `output/presets/bgm/` 不存在 |
| 调色 | 19 预设 + 关键帧 + WebGL 实时预览 | 8 预设 + 服务端单帧预览，关键帧降 P2 | 客户端不做重计算；批量场景下模板级统一即可 |
| 色彩一致性 | 只在后期补救 | 新增上游 Art Direction 色彩锚点 | 根因在生成端，后期 LUT 治标 |
| 剧本工作台 | 无 | V3 新增 2 周 | 短剧成败首要因素，v1.1 完全缺失 |
| 自动挑卡 | 无 | V1 新增 1 周 | 直接砍掉约一半人工点击量 |
| 成本 | V3 事后汇总 | V1 记账 + 熔断，V4 看板 | 事后账单救不了钱；防 bug 烧钱 |
| 口型对齐 | V3 质检里的「可选检查项」 | **移出本规划** | 无本地 GPU；云 API 方案需单独评估，不占用主线周期 |
| 内容合规 | 无 | 移出本规划 | 内部使用，人工审足够 |
| 总周期 | 24 周 | 29.5 周 | 新增首个成片 4 周、地基 6.5 周、剧本工作台 2 周、自动挑卡 1 周；删减自研剪辑器约 6 周、调色缩减约 1 周 |

---

## 11. 待办与开放问题

| # | 事项 | 何时决 | 说明 |
|---|---|---|---|
| Q1 | 是否把 6 预设全局调色加入 V-1（+1 周） | V-1.6 基线报告后 | 取决于实测分镜色调跳变是否严重到影响发布 |
| Q2 | V0/V1 排期是否需要修正 | V-1 结束 | 基线报告会给出真实耗时/失败率/人工点击数，届时复评 |
| Q3 | 各家云 API 并发上限标定 | V1 上线后 | 已决策推后；届时做阶梯实验，把实测值写进 §4.3 配置 |
| Q4 | BGM 素材来源与授权 | V-1.2 前 | 优先 CC0（Pixabay Music / Free Music Archive）；条款需逐条核实 |
| Q5 | 口型对齐（云 API 方案） | V4 后单独评估 | 无本地 GPU；不占用主线周期 |

---

> **下一步**：本文档评审通过后，先为 **V-1「首个完整成片」** 生成实施计划（Implementation Plan）进入开发。V-1 结束产出基线报告，据此复评 V0 与 V1 的排期与内容，再逐期推进。
>
> V-1.1「数据安全急救」与 V-1.2「BGM 素材落地」可在评审期间先行实施 —— 前者修复的是现存数据丢失路径，后者是零代码改动。
