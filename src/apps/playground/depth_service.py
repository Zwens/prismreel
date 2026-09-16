"""Depth-video preprocessing jobs for the dance-swap flow.

Runs Video Depth Anything on the user's own GPU to turn a reference dance clip
into a grayscale depth video. That depth video is the motion signal handed to
the video model in the final step.

Jobs are tracked in memory rather than in PlaygroundStorage: a run takes
seconds, produces a file on disk, and has no cost or quota attached, so there
is nothing worth surviving a restart. The output path is what matters, and that
is returned to the client and then referenced like any other uploaded media.
"""

import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Optional

from ...models.depth_video import DepthVideoModel, DepthVideoError
from ...utils import get_logger
from ...utils.media_refs import to_posix_media_path

logger = get_logger(__name__)

DEPTH_OUTPUT_DIR = os.path.join("output", "playground", "depth")


@dataclass
class DepthJob:
    id: str
    source_video: str
    status: str = "pending"          # pending | processing | completed | failed
    progress: float = 0.0
    message: str = ""
    output_path: Optional[str] = None
    error: Optional[str] = None
    info: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)


class DepthJobManager:
    """Serialises depth runs and exposes their progress.

    Runs are serialised deliberately. Two concurrent depth jobs on one consumer
    GPU do not go faster — they either thrash VRAM or, on Windows, silently
    spill into system RAM and both crawl. A lock is the honest representation
    of "there is one GPU".
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, DepthJob] = {}
        self._gpu_lock = threading.Lock()

    # -- queries ---------------------------------------------------------

    def get(self, job_id: str) -> Optional[DepthJob]:
        return self._jobs.get(job_id)

    @staticmethod
    def capability() -> Dict:
        return DepthVideoModel.device_report()

    # -- execution -------------------------------------------------------

    def create(self, source_video: str) -> DepthJob:
        job = DepthJob(id=str(uuid.uuid4()), source_video=source_video)
        self._jobs[job.id] = job
        return job

    def run(
        self,
        job_id: str,
        *,
        encoder: str = "auto",
        input_size: Optional[int] = None,
        max_seconds: Optional[float] = None,
        target_fps: Optional[float] = None,
        contrast: str = "percentile",
    ) -> None:
        """Execute a job. Intended to be handed to BackgroundTasks."""
        job = self._jobs.get(job_id)
        if job is None:
            logger.warning("Depth job %s vanished before it ran", job_id)
            return

        def on_progress(pct: float, message: str) -> None:
            job.progress = round(float(pct), 3)
            job.message = message

        try:
            job.status = "processing"
            os.makedirs(DEPTH_OUTPUT_DIR, exist_ok=True)
            out_path = os.path.join(DEPTH_OUTPUT_DIR, f"depth_{job.id}.mp4")

            with self._gpu_lock:
                model = DepthVideoModel(encoder)
                info = model.generate(
                    job.source_video,
                    out_path,
                    input_size=input_size,
                    max_seconds=max_seconds,
                    target_fps=target_fps,
                    contrast=contrast,
                    progress_cb=on_progress,
                )

            job.output_path = to_posix_media_path(out_path)
            job.info = info
            job.status = "completed"
            job.progress = 1.0
            job.message = "完成"
            logger.info(
                "Depth job %s done: %s frames in %.1fs (%s @ %d, peak %.2f GB)",
                job.id, info["frames"], info["elapsed_sec"],
                info["encoder"], info["input_size"], info.get("peak_vram_gb") or 0.0,
            )
        except DepthVideoError as exc:
            # Already phrased for the user — pass it through verbatim.
            job.status, job.error = "failed", str(exc)
            logger.warning("Depth job %s failed: %s", job.id, exc)
        except Exception as exc:  # noqa: BLE001 - surface anything else too
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            logger.exception("Depth job %s crashed", job.id)
