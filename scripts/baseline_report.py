"""Collect V-1 baseline metrics from the on-disk store and rendered output.

Usage:
    python scripts/baseline_report.py --series-id <id>
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.media_probe import probe_duration  # noqa: E402


def _probe_merged_duration(merged: str) -> float:
    """Resolve merged_video_url to a real file and probe its duration.

    pipeline.merge_videos() stores merged_video_url as "videos/<file>.mp4"
    (plural) so it matches the /files/videos HTTP route mounted by
    apps/comic_gen/api.py (api.py:119: StaticFiles("/files/videos" ->
    "output/video")). The value is therefore route-relative, not
    filesystem-relative: the actual file lives under "output/video/"
    (singular). Naively joining "output" + merged_video_url yields
    "output/videos/<file>.mp4", which does not exist, so try the stored
    path first and fall back to the singular "video/" directory that the
    static mount actually serves from. This is a known single/plural
    debt (see progress.md) that is out of scope to fix here.
    """
    candidates = [
        os.path.join("output", merged),
        os.path.join("output", merged.replace("videos/", "video/", 1)),
    ]
    for path in candidates:
        try:
            return probe_duration(path)
        except Exception:
            continue
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--store", default="output/projects.json")
    args = parser.parse_args()

    with open(args.store, "r", encoding="utf-8") as f:
        scripts = json.load(f)

    episodes = [s for s in scripts.values() if s.get("series_id") == args.series_id]
    episodes.sort(key=lambda s: s.get("episode_number") or 0)
    if not episodes:
        print(f"No episodes found for series {args.series_id}")
        return 1

    print(f"# V-1 Baseline — series {args.series_id}\n")
    print("| Ep | Shots | Video tasks | Completed | Failed | With dialogue | Merged | Duration |")
    print("|----|-------|-------------|-----------|--------|---------------|--------|----------|")

    totals = {"shots": 0, "tasks": 0, "done": 0, "failed": 0, "dialogue": 0, "dur": 0.0}

    for ep in episodes:
        frames = ep.get("frames") or []
        tasks = ep.get("video_tasks") or []
        done = sum(1 for t in tasks if t.get("status") == "completed")
        failed = sum(1 for t in tasks if t.get("status") == "failed")
        with_dialogue = sum(1 for fr in frames if (fr.get("dialogue") or "").strip())

        merged = ep.get("merged_video_url")
        duration = 0.0
        if merged:
            duration = _probe_merged_duration(merged)

        print(
            f"| {ep.get('episode_number')} | {len(frames)} | {len(tasks)} | {done} | "
            f"{failed} | {with_dialogue} | {'yes' if merged else 'NO'} | {duration:.1f}s |"
        )

        totals["shots"] += len(frames)
        totals["tasks"] += len(tasks)
        totals["done"] += done
        totals["failed"] += failed
        totals["dialogue"] += with_dialogue
        totals["dur"] += duration

    attempts = totals["done"] + totals["failed"]
    rate = (totals["done"] / attempts * 100) if attempts else 0.0
    per_shot = (totals["tasks"] / totals["shots"]) if totals["shots"] else 0.0

    print("\n## Totals\n")
    print(f"- Episodes: {len(episodes)}")
    print(f"- Shots: {totals['shots']}")
    print(f"- Video tasks: {totals['tasks']}  (avg {per_shot:.2f} takes/shot)")
    print(f"- Success rate: {rate:.1f}%  ({totals['done']} ok / {totals['failed']} failed)")
    print(f"- Shots with dialogue: {totals['dialogue']}")
    print(f"- Total runtime: {totals['dur'] / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
