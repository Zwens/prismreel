"""Keep the developer's real .env out of the test process.

Importing src.apps.comic_gen.api runs load_dotenv(), so whichever test
module happens to import it first silently rewrites os.environ for
every module collected after it — OSS credentials appear, provider
routing flips to vendor mode, and tests asserting the unset defaults
fail purely on collection order. Snapshot and strip those keys up
front so the suite sees a clean environment regardless of order.
"""

import os

import pytest

_LEAKY_PREFIXES = ("OSS_",)
_LEAKY_KEYS = (
    "VIDU_PROVIDER_MODE",
    "KLING_PROVIDER_MODE",
    "PIXVERSE_PROVIDER_MODE",
)


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    for key in list(os.environ):
        if key in _LEAKY_KEYS or key.startswith(_LEAKY_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    yield
    # Stripping the env is not enough on its own: OSSImageUploader is a
    # singleton that reads the credentials once and caches a live bucket.
    # A test that reaches any endpoint going through signed_response builds
    # that instance while the real .env is still loaded, and every later
    # test then sees a configured uploader no matter what the environment
    # says — local-only assertions start receiving signed OSS URLs. Drop the
    # cached instance so the next test rebuilds it from its own environment.
    from src.utils.oss_utils import OSSImageUploader

    OSSImageUploader.reset_instance()
