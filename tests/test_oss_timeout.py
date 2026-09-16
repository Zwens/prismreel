"""The OSS client's timeout has to survive a real upload, not just a handshake.

oss2 passes ``connect_timeout`` straight to requests as a scalar ``timeout``,
so it caps the connect *and* the wait for the PUT response — and since OSS only
answers once the whole body is in, it caps the upload itself. At 5s a 691 KB
depth clip died with ``Read timed out`` on a normal home connection, and the
caller reported it as "Configure OSS for local/object-key references", pointing
at credentials that were fine.
"""

import pytest

from src.utils import oss_utils


@pytest.fixture
def captured_bucket(monkeypatch):
    """Build an uploader against a stubbed oss2, returning the Bucket kwargs."""
    captured = {}

    class _FakeBucket:
        def __init__(self, auth, endpoint, bucket_name, **kwargs):
            captured.update(kwargs)
            captured["endpoint"] = endpoint

    monkeypatch.setattr(oss_utils.oss2, "Auth", lambda *a, **k: object())
    monkeypatch.setattr(oss_utils.oss2, "Bucket", _FakeBucket)
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "secret")
    monkeypatch.setenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    monkeypatch.setenv("OSS_BUCKET_NAME", "bucket")
    oss_utils.OSSImageUploader.reset_instance()
    yield captured
    oss_utils.OSSImageUploader.reset_instance()


def test_timeout_is_long_enough_for_a_multi_megabyte_upload(captured_bucket):
    oss_utils.OSSImageUploader()

    assert captured_bucket["connect_timeout"] >= 30


def test_timeout_is_configurable(captured_bucket, monkeypatch):
    monkeypatch.setenv("OSS_TIMEOUT_SECONDS", "90")
    oss_utils.OSSImageUploader.reset_instance()

    oss_utils.OSSImageUploader()

    assert captured_bucket["connect_timeout"] == 90


def test_a_bad_timeout_value_falls_back_to_the_default(captured_bucket, monkeypatch):
    monkeypatch.setenv("OSS_TIMEOUT_SECONDS", "not-a-number")
    oss_utils.OSSImageUploader.reset_instance()

    oss_utils.OSSImageUploader()

    assert captured_bucket["connect_timeout"] == oss_utils.DEFAULT_OSS_TIMEOUT_SECONDS
