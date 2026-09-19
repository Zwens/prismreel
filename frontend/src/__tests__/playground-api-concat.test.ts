import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

vi.mock('axios');

describe('playgroundApi.concat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts video_paths and returns the combined path', async () => {
    (axios.post as any).mockResolvedValue({ data: { path: 'playground/videos/workflow_abc.mp4' } });
    const { playgroundApi } = await import('@/lib/api');

    const result = await playgroundApi.concat(['playground/videos/a.mp4', 'playground/videos/b.mp4']);

    expect(result).toEqual({ path: 'playground/videos/workflow_abc.mp4' });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/playground/concat'),
      { video_paths: ['playground/videos/a.mp4', 'playground/videos/b.mp4'] },
    );
  });
});
