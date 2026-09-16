import { API_URL } from './api';

/**
 * Output-relative, '/'-separated form of a stored media path.
 *
 * The backend serves `output/` at `/files/`, so the `output/` prefix has to go.
 * Paths persisted on Windows before the backend normalized its separators read
 * `output\playground\images\x.png`; the browser rewrites the backslashes to
 * slashes when it parses the URL, so stripping the prefix first would leave a
 * stray `output/` segment and a 404.
 */
export function toMediaRelativePath(path: string): string {
    return path.replace(/\\/g, '/').replace(/^\/+/, '').replace(/^output\//, '');
}

/** Browser-loadable URL for a stored media path. Absolute URLs pass through. */
export function mediaUrl(path: string): string {
    if (/^(https?:|blob:|data:)/i.test(path)) return path;
    return `${API_URL}/files/${toMediaRelativePath(path)}`;
}
