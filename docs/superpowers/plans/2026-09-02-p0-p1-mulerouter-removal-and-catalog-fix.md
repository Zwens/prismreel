# P0 + P1：移除 MuleRouter 与修正 Seedance Catalog 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 MuleRouter 网关及其独占的 gpt-image family，让 Seedance 全系列只走 BytePlus Ark 直连；同时修正 catalog 中三处会导致请求失败的分辨率错误，并把厂商计费数据落进独立的 `pricing.yaml`。

**Architecture:** 分两段。P0 是纯删除：先把两个消费方（playground service、comic pipeline）的网关分支收敛成单一 Ark 路径，再删掉 `src/models/mulerouter.py` 与前端凭证 UI。P1 是纯数据：按厂商文档改正 `seedance.yaml` 的 duration/resolution/ratio，新增 2.0-mini，再引入 `pricing.yaml` 与其加载、校验管线。两段都不需要 Ark 模型开通即可完整验证。

**Tech Stack:** Python 3.11 / FastAPI / pytest；Next.js 14 / TypeScript / vitest；YAML model catalog + 生成式 JSON 镜像。

**Spec:** `docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md`

## Global Constraints

- Node **18+**，本机已全局切到 **v24.14.0**；Python **3.11+**，虚拟环境在 `.venv/`。
- Ark base URL：`https://ark.ap-southeast.bytepluses.com/api/v3`，由 `ARK_REGION=intl` 决定。
- 所有 Seedance 模型的 `resolution.default` 一律为 **`720p`**（对齐厂商默认，spec D1）。
- 计费**原价入库**，限时折扣放 `promotions` 且必须带 `ends_at`（spec D3）。
- Commit message 遵循 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `chore:` / `test:`）。
- **不要使用 `git add .`**，逐一列出文件。
- 每次改动 catalog YAML 后必须依次运行 `python scripts/build_model_catalog.py` 与 `python scripts/validate_model_catalog.py`。
- 本仓库为 GitHub 公开仓库，推送前走 `prismreel-git-publish` 流程。

## File Structure

**删除**

| 文件 | 原职责 |
|---|---|
| `src/models/mulerouter.py`（630 行） | MuleRouter HTTP + MuleRun CLI 两种模式的视频/图像适配器 |
| `tests/test_mulerouter_seedance_body.py` | MuleRouter 请求体构造测试 |
| `docs/api-reference/seedance-mulerouter.md` | MuleRouter 侧 Seedance 文档镜像 |
| `config/model_catalog/families/gpt-image.yaml` | gpt-image-2（MuleRouter 独占） |

**新建**

| 文件 | 职责 |
|---|---|
| `config/model_catalog/pricing.yaml` | 按 model id 的厂商计价数据，与能力定义解耦 |
| `tests/test_model_pricing.py` | pricing 加载、合并、折扣过期判定 |
| `tests/test_seedance_catalog_params.py` | 断言 catalog 的分辨率/时长与厂商文档一致 |

**修改**

| 文件 | 改动 |
|---|---|
| `src/models/byteplus.py` | `ARK_MODEL_IDS` 补全 2.0/fast/mini；`resolve_model_id` 提为模块级纯函数并识别规范 id |
| `src/apps/playground/service.py` | 删除 MuleRouter 视频/图像分支与两个缓存字段 |
| `src/apps/comic_gen/pipeline.py` | 删除 `use_mulerouter` 分支与缓存字段 |
| `src/models/factory.py` | 删除 seedance → MuleRouter 分支 |
| `src/models/image.py` | 删除 `gpt-image` → mulerouter 映射 |
| `src/utils/endpoints.py` | 删除 `MULEROUTER` 端点 |
| `src/utils/provider_registry.py` | `SUPPORTED_PROVIDER_BACKENDS` 去掉 `mulerouter` |
| `src/utils/model_catalog.py` | 同上；新增 pricing 加载与合并 |
| `src/apps/comic_gen/api.py` | 删除 `MULEROUTER_API_KEY` 与 `MULERUN_CLI_LOGGED_IN` |
| `scripts/validate_model_catalog.py` | 新增 pricing 覆盖校验 |
| `config/model_catalog/families/seedance.yaml` | 只留 byteplus backend；修正参数；新增 2.0-mini |
| `tests/test_seedance_variant_routing.py` | 改为断言 Ark model id 解析 |
| `frontend/src/components/settings/SettingsPage.tsx` | 删除 MuleRouter/MuleRun 凭证区块 |
| `frontend/src/components/project/EnvConfigDialog.tsx` | 同上 |
| `frontend/src/lib/modelCatalog.ts` | 更新注释 |
| `frontend/src/__tests__/provider-credentials.test.ts` | 期望改为 `ARK_API_KEY` |
| `frontend/messages/{zh,en}.json` | 删除 `mulerun*` 文案键，更新 `arkHint` |
| `README.md` / `README_EN.md` | 更新 provider 说明 |

---

### Task 1: Seedance 视频路由收敛到 Ark

把两个消费方的「2.0 走 MuleRouter，2.5 走 Ark」二分支砍成单一 Ark 路径。同时补上被删解析器留下的缺口：`resolve_model_id` 目前只做字典直查，不认 catalog 的规范 id（`seedance/seedance-2.0-fast-video#t2v`），迁移后 fast 变体会静默按标准版计费。

**Files:**
- Modify: `src/models/byteplus.py:41-49`（`ARK_MODEL_IDS`）、`src/models/byteplus.py:103-109`（`resolve_model_id`）
- Modify: `src/apps/playground/service.py:377-419`、`src/apps/playground/service.py:43-45`
- Modify: `src/apps/comic_gen/pipeline.py:3325-3360`、`src/apps/comic_gen/pipeline.py:94`
- Modify: `src/models/factory.py:18-20`
- Test: `tests/test_seedance_variant_routing.py`（改写）

**Interfaces:**
- Produces: `src.models.byteplus.resolve_ark_model_id(model_name: Optional[str]) -> Optional[str]` —— 模块级纯函数，输入扁平 id 或规范 id，返回 Ark 线上 model id。Task 5 的 catalog 断言依赖它。
- Produces: `ARK_MODEL_IDS: Dict[str, str]` 覆盖 seedance 2.0 / 2.0-fast / 2.0-mini / 2.5 的全部 mode。

- [ ] **Step 1: 改写路由测试为失败态**

把 `tests/test_seedance_variant_routing.py` 整个替换成：

```python
"""Seedance 变体必须按调用解析，且只走 Ark。

模型实例是缓存复用的（pipeline 的 self._byteplus_video_model），所以变体必须
每次调用现算。存到实例上会让上一次的选择泄漏到下一次生成里。

fast / mini 与标准版计费不同（fast 720p 约 0.12 USD/秒，标准版约 0.15），
所以「解析不出来就退回标准版」是有意为之的安全默认。
"""

import pytest

from src.models.byteplus import resolve_ark_model_id


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_plain_model_id_maps_to_the_standard_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-{mode}") == "dreamina-seedance-2-0-260128"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_fast_model_id_maps_to_the_fast_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-fast-{mode}") == "dreamina-seedance-2-0-fast-260128"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_mini_model_id_maps_to_the_mini_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-mini-{mode}") == "dreamina-seedance-2-0-mini-260615"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_25_model_id_maps_to_the_25_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.5-{mode}") == "dreamina-seedance-2-5-260628"


def test_canonical_mode_id_with_fast_is_recognised():
    """Catalog 规范 id 形如 seedance/seedance-2.0-fast-video#t2v。"""
    assert resolve_ark_model_id(
        "seedance/seedance-2.0-fast-video#t2v"
    ) == "dreamina-seedance-2-0-fast-260128"


def test_canonical_mode_id_without_variant_is_recognised():
    assert resolve_ark_model_id(
        "seedance/seedance-2.0-video#i2v"
    ) == "dreamina-seedance-2-0-260128"


def test_unknown_or_missing_model_id_returns_none():
    """调用方没传型号时不能猜；返回 None 让上层报错，而不是静默按标准版计费。"""
    assert resolve_ark_model_id(None) is None
    assert resolve_ark_model_id("") is None
    assert resolve_ark_model_id("something-else") is None


def test_consecutive_calls_do_not_leak_the_variant():
    """缓存的模型实例是共享的，解析必须是纯函数。"""
    fast = resolve_ark_model_id("seedance-2.0-fast-t2v")
    plain = resolve_ark_model_id("seedance-2.0-t2v")

    assert fast == "dreamina-seedance-2-0-fast-260128"
    assert plain == "dreamina-seedance-2-0-260128"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_seedance_variant_routing.py -v`
Expected: FAIL，`ImportError: cannot import name 'resolve_ark_model_id'`

- [ ] **Step 3: 实现 `resolve_ark_model_id` 并补全映射表**

替换 `src/models/byteplus.py:41-49` 的 `ARK_MODEL_IDS`：

```python
# Catalog ids -> the id Ark expects on the wire. Both the flat legacy id
# (seedance-2.0-fast-t2v) and the catalog canonical id
# (seedance/seedance-2.0-fast-video#t2v) have to resolve, because playground
# holds the former and the comic pipeline holds the latter.
ARK_MODEL_IDS = {
    "seedance-2.0-t2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-i2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-r2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-fast-t2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-fast-i2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-fast-r2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-mini-t2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.0-mini-i2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.0-mini-r2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.5-t2v": "dreamina-seedance-2-5-260628",
    "seedance-2.5-i2v": "dreamina-seedance-2-5-260628",
    "seedance-2.5-r2v": "dreamina-seedance-2-5-260628",
}
```

在 `ARK_MODEL_IDS` 之后新增模块级纯函数：

```python
def resolve_ark_model_id(model_name: Optional[str]) -> Optional[str]:
    """Map a catalog id to the wire model id Ark expects.

    Pure by design: the model instance is cached and shared across tasks, so
    resolving into instance state would let one shot's variant leak into the
    next. Returns None for anything unrecognised rather than defaulting to the
    standard variant — fast and mini bill differently, so a silent fallback
    would misbill instead of failing loudly.
    """
    if not model_name:
        return None

    flat = model_name.strip().lower()
    if flat in ARK_MODEL_IDS:
        return ARK_MODEL_IDS[flat]

    # Canonical form: seedance/seedance-2.0-fast-video#t2v
    if "#" in flat:
        family_part, _, mode = flat.partition("#")
        base = family_part.rsplit("/", 1)[-1]
        if base.endswith("-video"):
            base = base[: -len("-video")]
        candidate = f"{base}-{mode}"
        if candidate in ARK_MODEL_IDS:
            return ARK_MODEL_IDS[candidate]

    return None
```

把 `src/models/byteplus.py:103-109` 的实例方法改为委托：

```python
    def resolve_model_id(self, model_name: Optional[str]) -> Optional[str]:
        return resolve_ark_model_id(model_name)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python -m pytest tests/test_seedance_variant_routing.py -v`
Expected: PASS，13 passed

- [ ] **Step 5: 收敛 playground service 的路由分支**

`src/apps/playground/service.py:43-45`，删掉这两行：

```python
        self._mulerouter_video_model = None
        self._mulerouter_image_model = None
```

保留 `self._byteplus_video_model = None`。

把 `src/apps/playground/service.py:377-419` 的 docstring 与二分支替换为：

```python
    def _generate_video_seedance(self, gen: PlaygroundGeneration, out_path: str) -> None:
        """Seedance runs entirely on BytePlus Ark.

        The family used to straddle two gateways; MuleRouter is gone, so there
        is a single path now.
        """
        params = gen.parameters
        img_path, img_url = self._resolve_first_input_media(gen)

        kwargs = {
            "duration": params.get("duration", 5),
            "resolution": params.get("resolution", "720p"),
            "aspect_ratio": params.get("aspect_ratio", "adaptive"),
            "seed": params.get("seed"),
            "watermark": params.get("watermark", False),
            # The adapter derives the wire model id (2.0 vs fast vs mini vs
            # 2.5) from this. Playground never sent it, so every fast-variant
            # run here silently billed and rendered as the standard variant.
            "model_name": gen.model_id,
        }

        # r2v: reference images
        if gen.mode == PlaygroundMode.R2V and gen.input_media:
            kwargs["generation_mode"] = "r2v"
            kwargs["ref_image_urls"] = list(gen.input_media)

        from ...models.byteplus import BytePlusVideoModel

        if self._byteplus_video_model is None:
            self._byteplus_video_model = BytePlusVideoModel({})
        model = self._byteplus_video_model
```

其后原有的 `model.generate(...)` 调用保持不变。

同时把文件头 `src/apps/playground/service.py:4` 的模块 docstring 里
`MuleRouterVideoModel/ImageModel` 改为 `BytePlusVideoModel`。

- [ ] **Step 6: 收敛 comic pipeline 的路由分支**

`src/apps/comic_gen/pipeline.py:94`，删掉：

```python
        self._mulerouter_video_model = None
```

把 `src/apps/comic_gen/pipeline.py:3325-3331` 的两处判断替换为：

```python
            # Seedance runs entirely on BytePlus Ark; the MuleRouter gateway
            # this family used to share has been removed.
            use_byteplus = backend == "byteplus" or model_name_lower.startswith("seedance")
```

删除 `use_mulerouter` 变量，并把随后的 `elif use_mulerouter:` 整个分支（`pipeline.py:3351` 起至该分支结束）连同其 `self._mulerouter_video_model` 构造与 `generate(...)` 调用一并删除。`if use_byteplus:` 分支保持不变。

- [ ] **Step 7: 删除 factory 的 seedance 分支**

`src/models/factory.py:18-20`，删掉：

```python
        elif model_name in ('seedance', 'seedance-2.0'):
            from .mulerouter import MuleRouterVideoModel
            return MuleRouterVideoModel(config.get('model') or {})
```

- [ ] **Step 8: 运行后端测试确认无回归**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS。`tests/test_mulerouter_seedance_body.py` 此时仍会失败（它 import 尚未删除的 mulerouter 模块，Task 3 才删）——若失败仅限该文件，可继续；其余任何失败都必须先修。

- [ ] **Step 9: 提交**

```bash
git add src/models/byteplus.py src/apps/playground/service.py src/apps/comic_gen/pipeline.py src/models/factory.py tests/test_seedance_variant_routing.py
git commit -m "refactor: route the whole Seedance family through Ark"
```

---

### Task 2: 删除 gpt-image family 与图像路由分支

gpt-image-2 是 MuleRouter 独占（`src/models/mulerouter.py:87` `MULEROUTER_ONLY_MODELS`）。按 spec D7 整体删除，不改走 OpenAI 直连。

**Files:**
- Delete: `config/model_catalog/families/gpt-image.yaml`
- Modify: `src/models/image.py:886-889`
- Modify: `src/apps/playground/service.py:198-199`、`src/apps/playground/service.py:271-291`
- Regenerate: `config/model_catalog/generated/model_catalog.json`、`frontend/src/generated/modelCatalog.json`

**Interfaces:**
- Consumes: 无
- Produces: catalog 中不再存在 `gpt-image` family 与 `gpt-image-2` 模型；`_image_provider_for("gpt-image-2")` 返回 `""`。

- [ ] **Step 1: 删除 family 文件**

```bash
git rm config/model_catalog/families/gpt-image.yaml
```

- [ ] **Step 2: 删除图像 provider 映射**

`src/models/image.py:886-887`，删掉：

```python
    if name.startswith("gpt-image"):
        return "mulerouter"
```

- [ ] **Step 3: 删除 playground 的图像分支**

`src/apps/playground/service.py:198-199`，把：

```python
                if model_lower.startswith("gpt-image"):
                    self._generate_image_mulerouter(gen, out_path, idx)
                elif is_vidu_image_model(model_lower):
```

改为：

```python
                if is_vidu_image_model(model_lower):
```

并删除整个 `_generate_image_mulerouter` 方法（`src/apps/playground/service.py:271-291`）。

- [ ] **Step 4: 重新生成 catalog 产物**

Run:
```bash
.venv/Scripts/python scripts/build_model_catalog.py
.venv/Scripts/python scripts/validate_model_catalog.py
```
Expected: build 打印三个写入路径；validate 通过。`catalog.meta.yaml` 的默认图像模型是 `wan2.7-image-pro`，不涉及被删模型，校验不应因默认值报错。

- [ ] **Step 5: 确认 catalog 里已无 gpt-image**

Run: `grep -ri "gpt-image" config/ frontend/src/generated/ src/ ; echo "exit=$?"`
Expected: 无输出，`exit=1`

- [ ] **Step 6: 运行测试**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 除 `tests/test_mulerouter_seedance_body.py` 外全部 PASS

- [ ] **Step 7: 提交**

```bash
git add -u config/model_catalog src/models/image.py src/apps/playground/service.py
git add config/model_catalog/generated/model_catalog.json frontend/src/generated/modelCatalog.json
git commit -m "refactor: drop the MuleRouter-only gpt-image family"
```

---

### Task 3: 删除 MuleRouter 模块与后端配置项

此时已无消费方，可以安全删除模块本体。MuleRun CLI 模式也在这个模块里（`src/models/mulerouter.py:4-7`），一并移除。

**Files:**
- Delete: `src/models/mulerouter.py`、`tests/test_mulerouter_seedance_body.py`、`docs/api-reference/seedance-mulerouter.md`
- Modify: `src/utils/endpoints.py:8`、`src/utils/provider_registry.py:7`、`src/utils/model_catalog.py:9`
- Modify: `src/apps/comic_gen/api.py:1132`、`:4136`、`:4188`、`:4197`
- Modify: `config/model_catalog/families/seedance.yaml:1-31`

**Interfaces:**
- Consumes: Task 1 与 Task 2 已移除全部 import
- Produces: `SUPPORTED_PROVIDER_BACKENDS == ("dashscope", "vendor", "byteplus")`，两处定义保持一致

- [ ] **Step 1: 删除文件**

```bash
git rm src/models/mulerouter.py tests/test_mulerouter_seedance_body.py docs/api-reference/seedance-mulerouter.md
```

- [ ] **Step 2: 收窄 provider backends 常量**

`src/utils/provider_registry.py:7` 与 `src/utils/model_catalog.py:9` 两处都改为：

```python
SUPPORTED_PROVIDER_BACKENDS = ("dashscope", "vendor", "byteplus")
```

- [ ] **Step 3: 删除 endpoint 与配置键**

`src/utils/endpoints.py:8`，删掉：

```python
    "MULEROUTER": "https://api.mulerouter.ai",
```

`src/apps/comic_gen/api.py:1132`，删掉 `MULEROUTER_API_KEY: Optional[str] = None`；
`:4136` 从密钥集合里删掉 `"MULEROUTER_API_KEY",`；
`:4188` 删掉 `"MULEROUTER_API_KEY": _mask_secret(os.getenv("MULEROUTER_API_KEY")),`；
`:4197` 删掉 `"MULERUN_CLI_LOGGED_IN": _check_mulerun_cli_status(),`，
并删除 `_check_mulerun_cli_status` 函数定义本身。

- [ ] **Step 4: 让 seedance family 只剩一个 backend**

`config/model_catalog/families/seedance.yaml:1-31` 的头部替换为：

```yaml
family: seedance
display_name: "Seedance (即梦)"
provider: byteplus
routing_prefixes:
  - seedance-2.0-
  - seedance-2.5-
  - seedance/seedance-
supported_backends:
  - byteplus
default_backend: byteplus
credential_sources:
  byteplus:
    - ARK_API_KEY
supported_modalities:
  - t2v
  - i2v
  - r2v
docs:
  official_snapshot_ids:
    - byteplus/modelark-seedance/2026-09-02
transport:
  image_input_mode:
    # Ark takes an image_url item that may be a public URL or a data URI.
    byteplus: byteplus_ark_image_url
```

注意：`backend_env_key: SEEDANCE_PROVIDER_MODE` 一并删除（spec D6：family 只剩单一 backend，保留只有一个取值的开关是无谓分支）。

`seedance.yaml` 中每个 model 条目下的 `runtime.mulerouter:` 段全部删除，只保留
`runtime.byteplus:`。2.0 与 2.0-fast 原本没有 byteplus runtime，需按 Task 1 的映射补上
`api_model_id`（2.0 → `dreamina-seedance-2-0-260128`，fast → `dreamina-seedance-2-0-fast-260128`）。

- [ ] **Step 5: 全仓确认无残留**

Run: `grep -ril "mulerouter\|mulerun" --include=*.py --include=*.yaml src config tests scripts ; echo "exit=$?"`
Expected: 无输出，`exit=1`

- [ ] **Step 6: 重新生成并校验 catalog**

Run:
```bash
.venv/Scripts/python scripts/build_model_catalog.py
.venv/Scripts/python scripts/validate_model_catalog.py
```
Expected: 均通过

- [ ] **Step 7: 运行全部后端测试**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 全部 PASS，无 skip 掩盖的失败

- [ ] **Step 8: 提交**

```bash
git add -u src config tests docs
git add config/model_catalog/generated/model_catalog.json frontend/src/generated/modelCatalog.json
git commit -m "refactor: remove the MuleRouter gateway and its MuleRun CLI mode"
```

---

### Task 4: 前端移除 MuleRouter 凭证界面

**Files:**
- Modify: `frontend/src/components/settings/SettingsPage.tsx:49,52,60,77,739-800,835`
- Modify: `frontend/src/components/project/EnvConfigDialog.tsx:28,31,39,55,436-452`
- Modify: `frontend/src/lib/modelCatalog.ts:408-411`
- Modify: `frontend/src/__tests__/provider-credentials.test.ts`
- Modify: `frontend/messages/zh.json`、`frontend/messages/en.json`

**Interfaces:**
- Consumes: Task 3 产出的 catalog JSON 镜像里 seedance family 的 `credential_sources` 只剩 `byteplus: [ARK_API_KEY]`
- Produces: `modelRequiresCredentials('seedance-2.0-r2v')` 返回 `['ARK_API_KEY']`

- [ ] **Step 1: 改写凭证测试为失败态**

`frontend/src/__tests__/provider-credentials.test.ts` 中，把所有对 seedance 的期望从
`MULEROUTER_API_KEY` 改为 `ARK_API_KEY`，并更新文件头注释。核心断言改为：

```typescript
        expect(modelRequiresCredentials('seedance-2.0-r2v')).toEqual(['ARK_API_KEY']);
        expect(modelRequiresCredentials('seedance-2.0-fast-r2v')).toEqual(['ARK_API_KEY']);
        expect(modelRequiresCredentials('seedance-2.5-r2v')).toEqual(['ARK_API_KEY']);

        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: 'ark-live-x' })).toBe(true);
        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: '' })).toBe(false);
```

原第 29 行「Seedance spans two gateways」的注释改为说明整族只有一个凭证。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/__tests__/provider-credentials.test.ts`
Expected: FAIL，实际值仍为 `['MULEROUTER_API_KEY']`（若 Task 3 的 catalog 已重新生成，此步可能直接通过——那就直接进入 Step 3）

- [ ] **Step 3: 删除设置页的凭证区块**

`frontend/src/components/settings/SettingsPage.tsx`：
- `:49` 删除 `MULEROUTER_API_KEY: string;`
- `:52` 删除 `MULERUN_CLI_LOGGED_IN?: boolean;`
- `:60` 从端点列表里删除 `{ key: "MULEROUTER_BASE_URL", label: "MuleRouter", placeholder: "https://api.mulerouter.ai" },`
- `:77` 删除默认值 `MULEROUTER_API_KEY: "",`
- `:739-800` 删除整个 MuleRun 登录提示块、已登录提示块与 `MULEROUTER_API_KEY` 字段
- `:835` 把 `arkHint` 附近的注释从「不在 MuleRouter 网关上」改为说明 Ark 是 Seedance 的唯一网关

`frontend/src/components/project/EnvConfigDialog.tsx` 做同样的删除：`:28`、`:31`、`:39`、`:55`、`:436-452` 整个「MuleRun / MuleRouter」区块。

- [ ] **Step 4: 更新 i18n**

`frontend/messages/en.json` 与 `frontend/messages/zh.json` 删除这些键：
`mulerunLabel`、`mulerunHint`、`mulerunLogin`、`mulerunLoggedIn`、`mulerunKeyHint`。

把 `arkHint` 从
`"Used by Seedance 2.5. It does not run on the MuleRouter gateway and needs its own Ark key."`
改为
`"Used by the whole Seedance family, which runs on BytePlus Ark."`
（zh.json 对应改为「Seedance 全系列使用，运行在 BytePlus Ark 上。」）

- [ ] **Step 5: 更新 modelCatalog.ts 注释**

`frontend/src/lib/modelCatalog.ts:408-411` 的注释改为：

```typescript
    // Narrow to the backend this particular model runs on. A family can span
    // backends, so flattening every backend's keys would call a model ready
    // just because an unrelated backend's credential happens to be set.
```

- [ ] **Step 6: 运行前端测试与类型检查**

Run:
```bash
cd frontend && npm run typecheck && npx vitest run src/__tests__/provider-credentials.test.ts
```
Expected: typecheck 无错误；凭证测试 PASS

- [ ] **Step 7: 全仓确认无残留**

Run: `grep -ril "mulerouter\|mulerun" frontend/src frontend/messages ; echo "exit=$?"`
Expected: 无输出，`exit=1`

- [ ] **Step 8: 更新 README**

`README.md` 与 `README_EN.md` 中列出 provider 的段落，删除 MuleRouter/MuleRun 条目，
并把 Seedance 的 provider 标注为 BytePlus Ark。

- [ ] **Step 9: 提交**

```bash
git add -u frontend/src frontend/messages README.md README_EN.md
git commit -m "refactor(frontend): drop the MuleRouter credential surface"
```

---

### Task 5: 修正 Seedance catalog 参数并新增 2.0-mini

按 `docs/api-reference/byteplus-ark-seedance-seedream.md` 第 2.1–2.3 节修正。三处现存错误：2.5 挂了它没有的 4K、2.0 缺了它有的 4K、2.0-fast 开放了它不支持的 1080p。

**Files:**
- Modify: `config/model_catalog/families/seedance.yaml`（全部 model 条目）
- Test: `tests/test_seedance_catalog_params.py`（新建）

**Interfaces:**
- Consumes: Task 3 产出的单 backend family 头部
- Produces: catalog 中新增 `seedance/seedance-2.0-mini-video` 及其三个 mode，legacy id 为 `seedance-2.0-mini-{t2v,i2v,r2v}`（与 Task 1 的 `ARK_MODEL_IDS` 键一致）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_seedance_catalog_params.py`：

```python
"""Catalog 的 Seedance 参数必须与厂商文档一致。

依据：docs/api-reference/byteplus-ark-seedance-seedream.md（2026-09-02 抓取）。
在此之前 catalog 把 4K 挂在 2.5 上（它没有），2.0 上却没有（它有），
而 2.0-fast 开放了 1080p（它只到 720p）——三者都会让请求在 Ark 侧失败。
"""

import json
from pathlib import Path

import pytest

CATALOG = json.loads(
    (Path(__file__).resolve().parents[1]
     / "config" / "model_catalog" / "generated" / "model_catalog.json")
    .read_text(encoding="utf-8")
)
MODELS = CATALOG["models"]

MODES = ["t2v", "i2v", "r2v"]


@pytest.mark.parametrize("mode", MODES)
def test_25_has_no_4k(mode):
    params = MODELS[f"seedance-2.5-{mode}"]["params"]
    assert "4k" not in params["resolution"]["options"]
    assert params["resolution"]["options"] == ["480p", "720p", "1080p"]


@pytest.mark.parametrize("mode", MODES)
def test_20_standard_has_4k(mode):
    params = MODELS[f"seedance-2.0-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p", "1080p", "4k"]


@pytest.mark.parametrize("mode", MODES)
def test_20_fast_tops_out_at_720p(mode):
    params = MODELS[f"seedance-2.0-fast-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p"]


@pytest.mark.parametrize("mode", MODES)
def test_20_mini_exists_and_tops_out_at_720p(mode):
    params = MODELS[f"seedance-2.0-mini-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p"]


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini", "2.5"]
    for m in MODES
])
def test_default_resolution_matches_the_vendor_default(model_id):
    """厂商默认是 720p；catalog 之前一律写死 1080p，画质与成本都对不上。"""
    assert MODELS[model_id]["params"]["resolution"]["default"] == "720p"


@pytest.mark.parametrize("mode", MODES)
def test_25_duration_range(mode):
    duration = MODELS[f"seedance-2.5-{mode}"]["duration"]
    assert (duration["min"], duration["max"]) == (4, 30)


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini"]
    for m in MODES
])
def test_20_family_duration_range(model_id):
    duration = MODELS[model_id]["duration"]
    assert (duration["min"], duration["max"]) == (4, 15)


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini", "2.5"]
    for m in MODES
])
def test_duration_advertises_the_auto_option(model_id):
    """厂商的 duration 支持 -1（自动）。2.5 的默认值就是 -1，而滑杆表达不了它，
    所以用一个独立的布尔位声明「本模型接受自动时长」。"""
    assert MODELS[model_id]["duration"]["allow_auto"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_seedance_catalog_params.py -v`
Expected: FAIL —— 2.5 含 4k、2.0 缺 4k、fast 含 1080p、默认值为 1080p、mini 的 key 不存在（KeyError）

- [ ] **Step 3: 修正 2.5 的三个 mode**

`config/model_catalog/families/seedance.yaml` 中 `seedance/seedance-2.5-video` 条目：
- `description` 里的 `up to 4K` 改为 `up to 1080p`
- 三个 mode 的 `params.resolution` 全部改为：

```yaml
          resolution:
            options: [480p, 720p, 1080p]
            default: 720p
```

- 三个 mode 的 `params` 中新增 `ratio`：

```yaml
          ratio:
            options: ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", adaptive]
            default: adaptive
```

- 三个 mode 的 `duration` 块末尾新增 `allow_auto: true`，即：

```yaml
        duration:
          type: slider
          min: 4
          max: 30
          step: 1
          default: 5
          allow_auto: true
```

`allow_auto` 需要在 `src/utils/model_catalog.py` 的 duration 规范化逻辑里透传到生成物
（与 `min`/`max`/`step`/`default` 同级），缺省为 `False`。前端的「自动」开关属 P4 范围，
本期只落数据。

- [ ] **Step 4: 修正 2.0 标准版的三个 mode**

`seedance/seedance-2.0-video` 条目的三个 mode，`params.resolution` 改为：

```yaml
          resolution:
            options: [480p, 720p, 1080p, 4k]
            default: 720p
```

并同样补上 Step 3 的 `ratio` 块与 `duration.allow_auto: true`（注意 2.0 家族是 `min: 4` / `max: 15`）。

- [ ] **Step 5: 修正 2.0-fast 的三个 mode**

`seedance/seedance-2.0-fast-video` 条目的三个 mode，`params.resolution` 改为：

```yaml
          resolution:
            options: [480p, 720p]
            default: 720p
```

并补上 `ratio` 块。

- [ ] **Step 6: 新增 2.0-mini**

在 `seedance/seedance-2.0-fast-video` 条目之后插入：

```yaml
  - id: seedance/seedance-2.0-mini-video
    display_name: Seedance 2.0 Mini
    description: ByteDance Seedance 2.0 Mini — cheapest draft tier, 480p/720p only
    status: active
    release_stage: stable
    docs:
      context_hub_doc_ids:
        - byteplus/modelark-seedance-2.0
    runtime:
      byteplus:
        gateway: byteplus
    modes:
      t2v:
        legacy_id: seedance-2.0-mini-t2v
        display_name: Seedance 2.0 Mini T2V
        description: Text-to-video, draft tier
        capabilities: [t2v]
        runtime:
          byteplus:
            api_model_id: dreamina-seedance-2-0-mini-260615
        ui:
          selection_group: t2v
          visible_in: [project_settings, series_settings, video_sidebar, global_settings]
          order: 80
          badges: [new]
        duration:
          type: slider
          min: 4
          max: 15
          step: 1
          default: 5
          allow_auto: true
        params:
          resolution:
            options: [480p, 720p]
            default: 720p
          ratio:
            options: ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", adaptive]
            default: adaptive
          seed: true
          negativePrompt: false
          promptExtend: false
          watermark: true
      i2v:
        legacy_id: seedance-2.0-mini-i2v
        display_name: Seedance 2.0 Mini I2V
        description: First-frame image to video, draft tier
        capabilities: [i2v]
        runtime:
          byteplus:
            api_model_id: dreamina-seedance-2-0-mini-260615
        ui:
          selection_group: i2v
          visible_in: [project_settings, series_settings, video_sidebar, global_settings]
          order: 80
          badges: [new]
        duration:
          type: slider
          min: 4
          max: 15
          step: 1
          default: 5
          allow_auto: true
        params:
          resolution:
            options: [480p, 720p]
            default: 720p
          ratio:
            options: ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", adaptive]
            default: adaptive
          seed: true
          negativePrompt: false
          promptExtend: false
          watermark: true
        inputs:
          reference_images:
            max: 1
            reference_type: image
      r2v:
        legacy_id: seedance-2.0-mini-r2v
        display_name: Seedance 2.0 Mini R2V
        description: Reference-to-video, draft tier
        capabilities: [r2v]
        runtime:
          byteplus:
            api_model_id: dreamina-seedance-2-0-mini-260615
        ui:
          selection_group: r2v
          visible_in: [project_settings, series_settings, video_sidebar, global_settings]
          order: 80
          badges: [new]
        duration:
          type: slider
          min: 4
          max: 15
          step: 1
          default: 5
          allow_auto: true
        params:
          resolution:
            options: [480p, 720p]
            default: 720p
          ratio:
            options: ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", adaptive]
            default: adaptive
          seed: true
          negativePrompt: false
          promptExtend: false
          watermark: true
        inputs:
          reference_images:
            max: 9
            reference_type: image
```

- [ ] **Step 7: 重新生成并运行测试**

Run:
```bash
.venv/Scripts/python scripts/build_model_catalog.py
.venv/Scripts/python scripts/validate_model_catalog.py
.venv/Scripts/python -m pytest tests/test_seedance_catalog_params.py -v
```
Expected: 三者全部通过

- [ ] **Step 8: 运行全部后端测试**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add config/model_catalog/families/seedance.yaml tests/test_seedance_catalog_params.py
git add config/model_catalog/generated/model_catalog.json frontend/src/generated/modelCatalog.json
git commit -m "fix: correct Seedance resolution tiers and add the 2.0 mini variant"
```

---

### Task 6: 引入 pricing.yaml 与其加载、校验管线

计价数据独立于能力定义（spec D3）。原价入库，限时折扣单独放 `promotions` 且必须带 `ends_at`。

**Files:**
- Create: `config/model_catalog/pricing.yaml`
- Modify: `src/utils/model_catalog.py`
- Modify: `scripts/validate_model_catalog.py`
- Test: `tests/test_model_pricing.py`（新建）

**Interfaces:**
- Consumes: Task 5 产出的 catalog 结构
- Produces: `src.utils.model_catalog.load_pricing() -> Dict[str, dict]`；生成物中每个模型多出 `pricing` 字段；`src.utils.model_catalog.active_promotions(pricing_entry, now) -> List[dict]`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_model_pricing.py`：

```python
"""计价数据与能力定义解耦，且折扣必须会过期。

原价入库、折扣单列，是因为限时活动到期后如果价格已被折后价覆盖，
就再也拿不回真实单价了。
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from src.utils.model_catalog import (
    GENERATED_MODEL_CATALOG_PATH,
    active_promotions,
    load_pricing,
)


def test_pricing_covers_every_active_video_model():
    pricing = load_pricing()
    for model_id in [
        "dreamina-seedance-2-5-260628",
        "dreamina-seedance-2-0-260128",
        "dreamina-seedance-2-0-fast-260128",
        "dreamina-seedance-2-0-mini-260615",
    ]:
        assert model_id in pricing, f"missing pricing for {model_id}"


def test_list_price_is_stored_not_the_discounted_one():
    """2.5 的 1080p 原价是 11.70；限时 28% off 只应出现在 promotions 里。"""
    entry = load_pricing()["dreamina-seedance-2-5-260628"]
    assert entry["online"]["1080p"]["without_video"] == 11.70
    assert entry["promotions"][0]["discount"] == 0.28


def test_reference_per_second_matches_the_vendor_table():
    """厂商给的典型场景折算：16:9、5 秒、无视频输入。"""
    entry = load_pricing()["dreamina-seedance-2-0-260128"]
    assert entry["reference_per_second"] == {
        "480p": 0.07, "720p": 0.15, "1080p": 0.37, "4k": 0.78,
    }


def test_expired_promotions_are_filtered_out():
    entry = {
        "promotions": [
            {"scope": ["1080p"], "discount": 0.28, "ends_at": "2026-09-17T14:00:00+08:00"},
        ]
    }
    before = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    after = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)

    assert len(active_promotions(entry, now=before)) == 1
    assert active_promotions(entry, now=after) == []


def test_pricing_is_merged_into_the_generated_catalog():
    catalog = json.loads(Path(GENERATED_MODEL_CATALOG_PATH).read_text(encoding="utf-8"))
    assert catalog["models"]["seedance-2.5-t2v"]["pricing"]["unit"] == "per_million_tokens"


def test_every_promotion_has_a_parsable_end_date():
    for model_id, entry in load_pricing().items():
        for promo in entry.get("promotions", []):
            assert "ends_at" in promo, f"{model_id} promotion without ends_at"
            dt.datetime.fromisoformat(promo["ends_at"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python -m pytest tests/test_model_pricing.py -v`
Expected: FAIL，`ImportError: cannot import name 'load_pricing'`

- [ ] **Step 3: 写 pricing.yaml**

新建 `config/model_catalog/pricing.yaml`。数据源见
`docs/api-reference/byteplus-ark-seedance-seedream.md` 第三节：

```yaml
version: 1
currency: USD

# Ark bills video by tokens; the per-second figures are the vendor's own
# worked examples (16:9, 5s, no video input) and exist for UI display only.
# List prices are stored here — never the discounted ones — so that a promo
# expiring does not leave the real rate unrecoverable.
models:
  dreamina-seedance-2-5-260628:
    unit: per_million_tokens
    online:
      "480p": { without_video: 10.70, with_video: 6.40 }
      "720p": { without_video: 10.70, with_video: 6.40 }
      "1080p": { without_video: 11.70, with_video: 7.00 }
    offline: null
    reference_per_second:
      "480p": 0.103
      "720p": 0.231
      "1080p": 0.569
    promotions:
      - scope: ["1080p"]
        discount: 0.28
        ends_at: "2026-09-17T14:00:00+08:00"

  dreamina-seedance-2-0-260128:
    unit: per_million_tokens
    online:
      "480p": { without_video: 7.00, with_video: 4.30 }
      "720p": { without_video: 7.00, with_video: 4.30 }
      "1080p": { without_video: 7.70, with_video: 4.70 }
      "4k": { without_video: 4.00, with_video: 2.40 }
    offline: null
    reference_per_second:
      "480p": 0.07
      "720p": 0.15
      "1080p": 0.37
      "4k": 0.78
    promotions: []

  dreamina-seedance-2-0-fast-260128:
    unit: per_million_tokens
    online:
      "480p": { without_video: 5.60, with_video: 3.30 }
      "720p": { without_video: 5.60, with_video: 3.30 }
    offline: null
    reference_per_second:
      "480p": 0.06
      "720p": 0.12
    promotions:
      - scope: ["480p", "720p"]
        discount: 0.25
        ends_at: "2026-09-07T14:00:00+08:00"

  dreamina-seedance-2-0-mini-260615:
    unit: per_million_tokens
    online:
      "480p": { without_video: 3.50, with_video: 2.10 }
      "720p": { without_video: 3.50, with_video: 2.10 }
    offline: null
    reference_per_second:
      "480p": 0.04
      "720p": 0.08
    promotions:
      - scope: ["480p", "720p"]
        discount: 0.60
        ends_at: "2026-09-07T14:00:00+08:00"
```

- [ ] **Step 4: 实现加载与合并**

在 `src/utils/model_catalog.py` 的路径常量区（`MODEL_CATALOG_SCHEMA_PATH` 附近）新增：

```python
MODEL_CATALOG_PRICING_PATH = MODEL_CATALOG_ROOT / "pricing.yaml"
```

在文件末尾新增：

```python
def load_pricing() -> Dict[str, Dict[str, Any]]:
    """Vendor pricing, keyed by the wire model id.

    Kept out of the family YAMLs because prices change far more often than
    capability definitions; a price edit should not churn the diff of a file
    that describes what a model can do.
    """
    if not MODEL_CATALOG_PRICING_PATH.exists():
        return {}
    raw = yaml.safe_load(MODEL_CATALOG_PRICING_PATH.read_text(encoding="utf-8")) or {}
    return raw.get("models", {})


def active_promotions(
    pricing_entry: Mapping[str, Any],
    now: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Promotions that have not expired yet.

    Callers pass `now` in tests; production reads the clock. An expired promo
    must disappear on its own — nobody is going to remember to prune it.
    """
    import datetime as _dt

    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)

    live = []
    for promo in pricing_entry.get("promotions", []) or []:
        ends_at = promo.get("ends_at")
        if not ends_at:
            continue
        deadline = _dt.datetime.fromisoformat(ends_at)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=_dt.timezone.utc)
        if deadline > now:
            live.append(promo)
    return live
```

再新增一个把 pricing 挂到单个 mode 上的辅助函数：

```python
def attach_pricing(
    model_entry: Dict[str, Any],
    pricing: Mapping[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach the vendor price for whichever wire model this mode calls.

    Writes an explicit None when there is no entry, rather than omitting the
    key: a consumer can then tell "no price data for this model" apart from
    "someone forgot to wire the field through".
    """
    api_model_id = (
        (model_entry.get("runtime") or {})
        .get("byteplus", {})
        .get("api_model_id")
    )
    model_entry["pricing"] = pricing.get(api_model_id) if api_model_id else None
    return model_entry
```

在生成 backend 产物的函数里，加载一次 pricing 并对每个 mode 调用它：

```python
    pricing = load_pricing()
    for model_entry in generated["models"].values():
        attach_pricing(model_entry, pricing)
```

前端 mirror 由同一份数据派生，无需单独处理。

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
.venv/Scripts/python scripts/build_model_catalog.py
.venv/Scripts/python -m pytest tests/test_model_pricing.py -v
```
Expected: PASS

- [ ] **Step 6: 给校验脚本加 pricing 覆盖检查**

在 `scripts/validate_model_catalog.py` 中新增：

```python
import datetime as dt

from src.utils.model_catalog import load_pricing

VIDEO_GROUPS = {"t2v", "i2v", "r2v"}


def check_pricing_coverage(catalog) -> list:
    """UI 上能选到的视频模型必须有价格。

    没有价格的模型会让成本提示静默消失，用户点下去才发现贵——比报错更糟。
    """
    problems = []
    covered = 0
    for model_id, entry in catalog["models"].items():
        ui = entry.get("ui") or {}
        if entry.get("status") != "active" or not ui.get("visible_in"):
            continue
        if ui.get("selection_group") not in VIDEO_GROUPS:
            continue
        if entry.get("pricing") is None:
            problems.append(f"{model_id}: visible and active but has no pricing entry")
        else:
            covered += 1
    print(f"- pricing: {covered} visible video model(s) priced")
    return problems


def check_promotion_dates() -> list:
    problems = []
    for model_id, entry in load_pricing().items():
        for promo in entry.get("promotions") or []:
            ends_at = promo.get("ends_at")
            if not ends_at:
                problems.append(f"{model_id}: promotion without ends_at")
                continue
            try:
                dt.datetime.fromisoformat(ends_at)
            except ValueError:
                problems.append(f"{model_id}: unparsable ends_at {ends_at!r}")
    return problems
```

在 `main()` 里把这两个函数的返回值并入既有的问题列表，任一非空即以非零码退出
并逐条打印。

- [ ] **Step 7: 运行校验**

Run: `.venv/Scripts/python scripts/validate_model_catalog.py`
Expected: 通过，且输出中包含 pricing 覆盖统计

- [ ] **Step 8: 提交**

```bash
git add config/model_catalog/pricing.yaml src/utils/model_catalog.py scripts/validate_model_catalog.py tests/test_model_pricing.py
git add config/model_catalog/generated/model_catalog.json frontend/src/generated/modelCatalog.json
git commit -m "feat: store vendor pricing alongside the model catalog"
```

---

### Task 7: 全量验证与发布

**Files:**
- 无新增改动；仅验证与推送

**Interfaces:**
- Consumes: Task 1–6 的全部产出

- [ ] **Step 1: 后端全量测试**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 2: 前端类型检查、测试、构建**

Run:
```bash
cd frontend && npm run typecheck
cd frontend && npm run test:all
cd frontend && npm run build
```
Expected: 三者全部通过

- [ ] **Step 3: catalog 产物一致性**

Run:
```bash
.venv/Scripts/python scripts/build_model_catalog.py
.venv/Scripts/python scripts/validate_model_catalog.py
git diff --stat config/model_catalog/generated frontend/src/generated
```
Expected: validate 通过；`git diff` 为空——若不为空说明有人改了 YAML 却没重新生成，必须提交产物

- [ ] **Step 4: MuleRouter 归零验收**

Run: `git grep -ri "mulerouter\|mulerun" -- ':(exclude)*prismreel-git-publish.md' ; echo "exit=$?"`
Expected: 无输出，`exit=1`（发布流程文档里那两条是扫描命令自身的文本，属误报，故排除）

- [ ] **Step 5: 启动应用做一次冒烟**

Run: `npm run dev`（需 Node 24），等待就绪后：
```bash
curl -s --noproxy '*' http://127.0.0.1:17177/health
curl -s --noproxy '*' http://127.0.0.1:17177/config/env
```
Expected: `/health` 返回 `ok:true`；`/config/env` 的返回里**不再包含** `MULEROUTER_API_KEY`
与 `MULERUN_CLI_LOGGED_IN`。前端 `http://localhost:3008` 的设置页不再出现 MuleRouter 区块。

- [ ] **Step 6: 走发布流程推送**

按 `.claude/commands/prismreel-git-publish.md` 执行敏感数据扫描后：

```bash
git push origin main
```

---

## 后续阶段（不在本计划内）

| 期 | 内容 | 阻塞条件 |
|---|---|---|
| P2 | Seedance 2.0 切 Ark 的实调验证 | 需 Ark 控制台开通模型 |
| P3 | vedit / vext 能力（catalog + 运行时 + 参数校验） | 需 P2 |
| P4 | Seedream 5.0 接入 + 独立「AI 视频」页 | 需 P1、P3 |

各自单独出计划。截至 2026-09-02，账号 `3004342898` 在 Ark 上仍未开通任何模型，
`python scripts/check_ark_activation.py` 可随时复检。
