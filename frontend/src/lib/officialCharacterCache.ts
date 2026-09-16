// Module-level cache mapping an `asset://<asset_id>` reference to display
// metadata (thumbnail, label). The playground store only holds the bare
// asset:// string (same shape as a local media path), so anything that
// needs to render a preview for it — MediaInput's SingleRefPreview and the
// multi-reference grid — looks it up here instead of carrying the full
// character object through store state.
//
// Read by MediaInput when rendering the current selection. A page reload
// loses the cache, which only affects the preview thumbnail/label — the
// asset:// URI itself is still sent to the backend correctly.
//
// NOTE: rememberOfficialCharacter currently has no caller. Its only writer was
// AssetPickerModal's "official characters" tab, and that component was removed
// when AssetSourcePicker replaced it — the two landed on separate branches and
// met in this merge. Everything else for the feature survived (backend route,
// thumbnails, the rendering path above), so re-enabling it means porting that
// tab in as a fifth source in AssetSourcePicker; the removed UI and its three
// i18n strings are recoverable from AssetPickerModal.tsx at origin/main~1.

export interface OfficialCharacterDisplay {
  thumbnailUrl: string;
  label: string;
}

const cache = new Map<string, OfficialCharacterDisplay>();

export function isOfficialCharacterRef(path: string): boolean {
  return path.startsWith('asset://');
}

export function rememberOfficialCharacter(path: string, display: OfficialCharacterDisplay): void {
  cache.set(path, display);
}

export function getOfficialCharacterDisplay(path: string): OfficialCharacterDisplay | undefined {
  return cache.get(path);
}
