# BGM 素材授权记录

## ⚠️ 当前状态：全部为占位音频，不可对外发布

以下 8 个文件由 `scripts/generate_placeholder_bgm.py` 用 ffmpeg 合成
（正弦和弦 + tremolo），仅用于验证渲染链路能正确混入 BGM。
它们不是可用的配乐，替换前不要用于任何对外分发的成片。

| 文件 | 状态 | 来源 | 作者 | 许可证 | 日期 |
|---|---|---|---|---|---|
| calm_warm.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| uplifting_pop.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| epic_cinematic.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| mystery_ambient.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| sad_piano.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| tension_drama.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| lofi_chill.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| fantasy_dreamy.mp3 | 占位 | ffmpeg 合成 | — | — | — |

## 替换真实素材时

1. 只用 CC0 / Public Domain。推荐：[Pixabay Music](https://pixabay.com/music/)
   （Pixabay Content License，允许商用免署名）、
   [Free Music Archive](https://freemusicarchive.org/) 的 CC0 条目。
   **不要用 CC-BY-NC**（禁止商用）。
2. **必须无人声** —— 有人声的 BGM 会与配音打架，sidechaincompress 也压不干净。
3. 时长 60-180 秒即可（渲染时 `-stream_loop -1` 自动循环）。
4. 文件名必须与 `src/apps/comic_gen/audio.py` 的 `BGM_PRESETS[*].url` 一致。
5. 替换后把上表该行的「状态」改为「已授权」并填齐来源/作者/许可证/日期。
