/**
 * Playground media paths -> /files URL.
 *
 * Stored paths come from the backend and are output-relative. Records written
 * on Windows before the backend normalized its separators are still in
 * playground_history.json as 'output\\playground\\images\\x.png', so the
 * prefix strip has to happen after separator normalization or the 'output'
 * segment survives into the URL and 404s.
 */
import { describe, it, expect } from 'vitest';
import { toMediaRelativePath } from '@/lib/mediaPath';

describe('toMediaRelativePath', () => {
    it('strips the output/ prefix from a posix path', () => {
        expect(toMediaRelativePath('output/playground/images/a.png')).toBe('playground/images/a.png');
    });

    it('normalizes Windows separators before stripping the prefix', () => {
        const raw = ['output', 'playground', 'uploads', 'a.png'].join('\\');
        expect(toMediaRelativePath(raw)).toBe('playground/uploads/a.png');
    });

    it('strips leading slashes', () => {
        expect(toMediaRelativePath('/output/playground/videos/a.mp4')).toBe('playground/videos/a.mp4');
    });

    it('leaves a path without the output prefix alone', () => {
        expect(toMediaRelativePath('assets/characters/a.png')).toBe('assets/characters/a.png');
    });
});
