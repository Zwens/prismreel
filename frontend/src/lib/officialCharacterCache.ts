// Module-level cache mapping an `asset://<asset_id>` reference to display
// metadata (thumbnail, label). The playground store only holds the bare
// asset:// string (same shape as a local media path), so anything that
// needs to render a preview for it — MediaInput's SingleRefPreview and the
// multi-reference grid — looks it up here instead of carrying the full
// character object through store state.
//
// Populated by AssetPickerModal when the user picks an official character;
// read by MediaInput when rendering the current selection. A page reload
// loses the cache, which only affects the preview thumbnail/label — the
// asset:// URI itself is still sent to the backend correctly.

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
