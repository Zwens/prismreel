#!/usr/bin/env python
"""为风格定调预设生成缩略图候选。

缩略图必须是该预设的**真实出图样本**，而不是另画的示意图——用户在卡片上看到什么，
套用后就该生成什么。所以这里刻意复刻 pipeline 里的提示词拼装方式
（见 src/apps/comic_gen/assets.py:603，场景描述在前、风格提示词在后，
negative_prompt 单独传），走同一个 WanxImageModel。

用法:
    # 给所有还没配图的预设各出 4 张候选
    python scripts/generate_style_thumbnails.py

    # 只跑指定预设，每个出 6 张
    python scripts/generate_style_thumbnails.py --preset xianxia_ethereal --count 6

    # 换模型 / 尺寸
    python scripts/generate_style_thumbnails.py --model qwen-image-2.0-pro --size 1280*1280

候选落在 output/style_thumbs/<preset_id>/cand_N.png，由人挑选定稿后再压缩、
按 {category}__{preset_id}__{scene_slug}__{orientation}.png 放进
frontend/public/assets/styles/，并回填 JSON 的 thumbnail 字段。
本脚本不自动定稿、不写 style_presets.json。
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.models.image import WanxImageModel  # noqa: E402  (needs .env loaded first)

PRESET_FILE = os.path.join(REPO_ROOT, "src", "apps", "comic_gen", "style_presets.json")
OUT_ROOT = os.path.join(REPO_ROOT, "output", "style_thumbs")

DEFAULT_MODEL = "wan2.7-image-pro"
# 模型档位里没有 4:3。方图对卡片（aspect-[4/3] + object-cover）和详情弹窗
# （object-contain 全图）两边都不吃亏，裁切焦点后续用 object_position 微调。
DEFAULT_SIZE = "1440*1440"


def load_presets():
    with open(PRESET_FILE, encoding="utf-8") as f:
        return json.load(f)["presets"]


def build_prompt(preset):
    """复刻 pipeline 的拼装顺序：具体场景在前，风格锚点在后。"""
    scene = preset.get("sample_prompt") or preset.get("description", "")
    return f"{scene}. {preset['positive_prompt']}"


def generate_one(model, preset, index, size, model_name):
    out_dir = os.path.join(OUT_ROOT, preset["id"])
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"cand_{index}.png")

    # 固定 seed，让候选可复现——挑中某张后想微调提示词重出同构图时不至于失手。
    path, secs = model.generate(
        build_prompt(preset),
        out_path,
        model_name=model_name,
        size=size,
        negative_prompt=preset.get("negative_prompt", ""),
        seed=1000 + index,
    )
    return preset["id"], index, path, secs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--preset", action="append", dest="presets", metavar="ID",
        help="只处理指定 preset id，可重复。默认处理所有未配 thumbnail 的预设",
    )
    ap.add_argument("--count", type=int, default=4, help="每个风格的候选数量（默认 4）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"T2I 模型（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--size", default=DEFAULT_SIZE, help=f"出图尺寸（默认 {DEFAULT_SIZE}）")
    ap.add_argument("--workers", type=int, default=4, help="并发数（默认 4）")
    args = ap.parse_args()

    if not os.getenv("DASHSCOPE_API_KEY"):
        sys.exit("DASHSCOPE_API_KEY 未配置，请检查项目根目录的 .env")

    all_presets = load_presets()
    by_id = {p["id"]: p for p in all_presets}

    if args.presets:
        unknown = [pid for pid in args.presets if pid not in by_id]
        if unknown:
            sys.exit(f"未知的 preset id: {unknown}\n可选: {sorted(by_id)}")
        targets = [by_id[pid] for pid in args.presets]
    else:
        targets = [p for p in all_presets if not p.get("thumbnail")]

    if not targets:
        print("没有需要生成缩略图的预设（所有预设都已配 thumbnail）。")
        print("如需重出，用 --preset <id> 指定。")
        return

    jobs = [(p, i) for p in targets for i in range(1, args.count + 1)]
    print(f"模型 {args.model} · 尺寸 {args.size} · {len(targets)} 个风格 × {args.count} 张 = {len(jobs)} 张")
    for p in targets:
        print(f"  - {p['id']}  {p.get('name_zh', '')}")
    print()

    model = WanxImageModel({})
    done = failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(generate_one, model, p, i, args.size, args.model): (p["id"], i)
            for p, i in jobs
        }
        for fut in as_completed(futures):
            pid, idx = futures[fut]
            try:
                _, _, path, secs = fut.result()
                done += 1
                print(f"[{done + failed}/{len(jobs)}] ✓ {pid} cand_{idx}  {secs:.1f}s  {os.path.relpath(path, REPO_ROOT)}")
            except Exception as e:
                failed += 1
                print(f"[{done + failed}/{len(jobs)}] ✗ {pid} cand_{idx}  {type(e).__name__}: {e}")

    print(f"\n完成 {done} 张，失败 {failed} 张。候选目录: {os.path.relpath(OUT_ROOT, REPO_ROOT)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
