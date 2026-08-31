"""The Seedance fast variant has to be selectable per call.

The runtime has always known the `-fast` endpoints, but `use_fast` was read
once from the constructor config and the pipeline builds the model with an
empty dict — so the fast paths were unreachable and the catalog could not
expose them honestly.

The model instance is CACHED and reused across tasks (`self._mulerouter_video_model`
in the pipeline), so the variant must be derived per call. Storing it on the
instance would let one shot's choice leak into the next shot's generation.
"""

import pytest

from src.models.mulerouter import resolve_seedance_endpoint


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_plain_model_id_routes_to_the_standard_endpoint(mode):
    path = resolve_seedance_endpoint(mode, "seedance-2.0-" + mode)

    assert "/seedance-2.0/" in path
    assert "-fast" not in path


@pytest.mark.parametrize("mode,segment", [
    ("t2v", "text-to-video"),
    ("i2v", "image-to-video"),
    ("r2v", "reference-to-video"),
])
def test_fast_model_id_routes_to_the_fast_endpoint(mode, segment):
    path = resolve_seedance_endpoint(mode, "seedance-2.0-fast-" + mode)

    assert "/seedance-2.0-fast/" in path
    assert segment in path


def test_unknown_or_missing_model_id_falls_back_to_standard():
    """A caller that never passes a model name must not silently get fast
    (which bills differently); standard is the safe default."""
    assert "-fast" not in resolve_seedance_endpoint("t2v", None)
    assert "-fast" not in resolve_seedance_endpoint("t2v", "")
    assert "-fast" not in resolve_seedance_endpoint("t2v", "something-else")


def test_canonical_mode_id_with_fast_is_recognised():
    """Catalog canonical ids look like seedance/seedance-2.0-fast-video#t2v."""
    path = resolve_seedance_endpoint("t2v", "seedance/seedance-2.0-fast-video#t2v")

    assert "/seedance-2.0-fast/" in path


def test_consecutive_calls_do_not_leak_the_variant():
    """The cached model instance is shared; resolution must be pure."""
    fast = resolve_seedance_endpoint("t2v", "seedance-2.0-fast-t2v")
    plain = resolve_seedance_endpoint("t2v", "seedance-2.0-t2v")

    assert "-fast" in fast
    assert "-fast" not in plain
