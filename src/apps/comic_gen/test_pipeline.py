import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from unittest.mock import patch

from src.apps.comic_gen.pipeline import ComicGenPipeline
from src.apps.comic_gen.models import GenerationStatus

def test_pipeline():
    print("Initializing Pipeline...")
    pipeline = ComicGenPipeline()
    
    print("\n--- Step 1: Create Project ---")
    novel_text = "Alex entered the ancient ruins. Suddenly, Luna appeared."
    script = pipeline.create_project("The Ancient Ruins", novel_text)
    print(f"Project Created: {script.id}")
    print(f"Characters: {len(script.characters)}")
    print(f"Scenes: {len(script.scenes)}")
    print(f"Frames: {len(script.frames)}")
    
    print("\n--- Step 2: Generate Assets ---")
    script = pipeline.generate_assets(script.id)
    for char in script.characters:
        print(f"Character {char.name}: {char.status} - {char.image_url}")
        
    print("\n--- Step 3: Generate Storyboard ---")
    script = pipeline.generate_storyboard(script.id)
    for frame in script.frames:
        print(f"Frame {frame.id}: {frame.status} - {frame.image_url}")
        
    print("\n--- Step 4: Generate Video ---")
    script = pipeline.generate_video(script.id)
    for frame in script.frames:
        print(f"Frame {frame.id} Video: {frame.status} - {frame.video_url}")
        
    print("\n--- Step 5: Generate Audio ---")
    script = pipeline.generate_audio(script.id)
    for frame in script.frames:
        print(f"Frame {frame.id} Audio: {frame.audio_url}")
        print(f"Frame {frame.id} SFX: {frame.sfx_url}")
        
    print("\nPipeline Test Completed.")

def test_create_project_forwards_owner_id_to_script_processor():
    from src.apps.comic_gen.pipeline import ComicGenPipeline

    pipeline = ComicGenPipeline()
    with patch.object(pipeline.script_processor, "create_draft_script") as mock_draft:
        mock_draft.return_value = pipeline.script_processor.create_draft_script("T", "text")
        pipeline.create_project("Title", "text", skip_analysis=True, owner_id="user-abc")

    script = list(pipeline.scripts.values())[-1]
    assert script.owner_id == "user-abc"


def test_video_generation_records_usage_for_byteplus(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.pipeline import ComicGenPipeline
    from src.apps.comic_gen.models import VideoTask

    pipeline = ComicGenPipeline()
    script = pipeline.create_project("Title", "text", skip_analysis=True, owner_id="user-xyz")
    task = VideoTask(id="task-1", project_id=script.id, image_url="", prompt="a cat", model="seedance-2.0-t2v", resolution="720p")
    script.video_tasks.append(task)

    with patch.object(pipeline, "_byteplus_video_model", None), \
         patch("src.models.byteplus.BytePlusVideoModel.generate") as mock_generate:
        mock_generate.return_value = ("output/video/task-1.mp4", 12.5, {"completion_tokens": 500000, "total_tokens": 500000})
        pipeline.process_video_task(script.id, "task-1")

    summary = usage_repo.get_user_usage_summary("user-xyz")
    assert summary["video"]["byteplus"]["dreamina-seedance-2-0-260128"]["total_tokens"] == 500000


def test_extract_preview_forwards_owner_id_as_user_id_to_parse_novel():
    from src.apps.comic_gen.pipeline import ComicGenPipeline

    pipeline = ComicGenPipeline()
    script = pipeline.create_project("Title", "text", skip_analysis=True, owner_id="user-preview")

    with patch.object(pipeline.script_processor, "parse_novel") as mock_parse_novel:
        mock_parse_novel.return_value = pipeline.script_processor.create_draft_script("Title", "new text")
        pipeline.extract_preview(script.id, "new text")

    _, kwargs = mock_parse_novel.call_args
    assert kwargs.get("user_id") == "user-preview"


if __name__ == "__main__":
    test_pipeline()
