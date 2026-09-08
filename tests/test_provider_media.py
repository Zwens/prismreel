import base64
from pathlib import Path

import pytest

from src.utils.provider_media import (
    RESOLVE_HEADER_DASHSCOPE_OSS_RESOURCE,
    resolve_media_input,
    resolve_media_inputs,
)


PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4//8/AwAI/AL+"
    "X2VINQAAAABJRU5ErkJggg=="
)


class FakeUploader:
    def __init__(self, configured: bool):
        self.is_configured = configured
        self.uploaded_paths = []

    def upload_file(self, local_path: str, sub_path: str = "", custom_filename=None):
        if not self.is_configured:
            return None
        self.uploaded_paths.append((local_path, sub_path))
        filename = custom_filename or Path(local_path).name
        return f"prismreel/{sub_path.strip('/')}/{filename}".replace("//", "/")

    def sign_url_for_api(self, object_key: str):
        return f"https://oss.example/{object_key}"


def _write_output_png(project_root: Path, rel_path: str) -> Path:
    output_root = project_root / "output"
    file_path = output_root / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(base64.b64decode(PNG_1X1_BASE64))
    return file_path


def test_vendor_kling_image_local_uses_plain_base64(tmp_path):
    _write_output_png(tmp_path, "uploads/ref.png")
    uploader = FakeUploader(configured=False)

    resolved = resolve_media_input(
        "uploads/ref.png",
        model_name="kling-v1",
        backend="vendor",
        modality="image",
        uploader=uploader,
        project_root=str(tmp_path),
    )

    assert not resolved.value.startswith("data:")
    assert resolved.value == PNG_1X1_BASE64
    assert resolved.headers == {}


def test_vendor_vidu_image_local_requires_url_capability(tmp_path):
    _write_output_png(tmp_path, "uploads/ref.png")
    uploader = FakeUploader(configured=False)

    with pytest.raises(ValueError, match="requires a URL-compatible media source"):
        resolve_media_input(
            "uploads/ref.png",
            model_name="vidu-q3",
            backend="vendor",
            modality="image",
            uploader=uploader,
            project_root=str(tmp_path),
        )


def test_vendor_url_mode_error_names_the_ref_and_its_classification(tmp_path):
    """An unresolvable ref must say which ref, and how it was classified.

    The bare "configure OSS" wording sent debugging down the wrong path when
    OSS was in fact configured and the ref itself was the unrecognized part.
    """
    uploader = FakeUploader(configured=True)

    with pytest.raises(ValueError) as excinfo:
        resolve_media_input(
            "totally-unknown-shape.png",
            model_name="vidu-q3",
            backend="vendor",
            modality="image",
            uploader=uploader,
            project_root=str(tmp_path),
        )

    message = str(excinfo.value)
    assert "totally-unknown-shape.png" in message
    assert "unknown" in message


def test_vendor_vidu_image_local_with_oss_uses_signed_url(tmp_path):
    _write_output_png(tmp_path, "uploads/ref.png")
    uploader = FakeUploader(configured=True)

    resolved = resolve_media_input(
        "uploads/ref.png",
        model_name="vidu-q3",
        backend="vendor",
        modality="image",
        uploader=uploader,
        project_root=str(tmp_path),
    )

    assert resolved.value.startswith("https://oss.example/prismreel/temp/provider_media/")


def test_resolver_does_not_mutate_input_refs(tmp_path):
    _write_output_png(tmp_path, "uploads/ref.png")
    uploader = FakeUploader(configured=False)
    refs = ["uploads/ref.png"]
    original = list(refs)

    resolved = resolve_media_inputs(
        refs,
        model_name="kling-v3-i2v",
        backend="vendor",
        modality="image",
        uploader=uploader,
        project_root=str(tmp_path),
    )

    assert refs == original
    assert len(resolved) == 1
    # vendor kling 走纯 base64（无 data: 前缀），断言只关心"入参没被改动"这条不变量。
    assert resolved[0].value
