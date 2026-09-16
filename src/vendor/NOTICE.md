# Vendored third-party code

## video_depth_anything/

Source: https://github.com/DepthAnything/Video-Depth-Anything
Copyright (2025) Bytedance Ltd. and/or its affiliates
License: Apache License 2.0 (see `video_depth_anything/LICENSE`)

Vendored at commit fetched 2026-09-14. Only the inference package is included;
the repo's training, benchmark and CLI code are not.

### Local modifications

1. `dinov2_layers/attention.py` — `Attention.forward` and
   `MemEffAttention.forward` now use `torch.nn.functional.
   scaled_dot_product_attention` instead of a materialised `B*H*N*N` softmax.

   Upstream only takes the memory-efficient path when `xformers` is installed
   and otherwise **silently** falls back to the naive implementation. On an
   8 GB card that fallback tries to allocate 11.4 GiB for a 5-second clip and
   dies with `torch.OutOfMemoryError`. torch >= 2.0 ships the same
   flash / mem-efficient kernels natively, so this removes the xformers
   dependency entirely rather than adding it.

   Measured on an RTX 4060 Laptop (8 GB), 121 frames @ 480x854, `vitl`,
   `input_size=518`: peak 7.9 GB, completes; upstream path OOMs.

2. `video_depth.py`, `video_depth_stream.py` — the upstream
   `from utils.util import ...` is an absolute import that only resolves when
   the repo root is the working directory. Rewritten to
   `from .util.vda_util import ...`, and the repo's `utils/util.py` is vendored
   as `util/vda_util.py`, so the package works from anywhere on sys.path.

No other files are modified.
