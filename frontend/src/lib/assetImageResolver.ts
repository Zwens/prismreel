import { characterImageUrl, characterSelectedVariant, selectedVariant } from "@/lib/characterImage";
import type { Character, ImageAsset, ImageVariant } from "@/store/projectStore";

/**
 * Normalisation point for the four-source asset picker.
 *
 * The global library, a series, a project's storyboard and the playground's own
 * generation history each store "the image of this thing" in a different shape,
 * and characters carry two schema eras on top of that. Every picker tab funnels
 * through resolveAssetMedia() so a new source can't reintroduce its own ad-hoc
 * unwrapping — and so a blank tile is a resolver bug with a test, not a mystery.
 */

export type AssetKind = "character" | "scene" | "prop" | "frame" | "generation";

export interface ResolvedMedia {
    /** The stored value, handed back to the caller for `input_media`. Either an
     *  absolute http(s) URL (OSS) or an output-relative path — the backend's
     *  `_resolve_first_input_media` accepts both. */
    path: string;
    /** Lets video-only / image-only slots filter without re-parsing the path. */
    type: "image" | "video";
}

const VIDEO_EXTENSIONS = /\.(mp4|mov|webm|avi|mkv)$/i;

function mediaType(path: string): "image" | "video" {
    return VIDEO_EXTENSIONS.test(path) ? "video" : "image";
}

function media(path: string | undefined | null): ResolvedMedia | null {
    return path ? { path, type: mediaType(path) } : null;
}

/** Scenes and props share one container shape: `image_asset` then `image_url`. */
function resolveImageAssetHolder(asset: { image_asset?: ImageAsset; image_url?: string }) {
    return media(selectedVariant(asset.image_asset)?.url || asset.image_url);
}

/**
 * A storyboard frame's picked image is the *active T2I candidate*, not its
 * first render — that history is what the R2V workbench actually shows, and
 * `t2i_selected_index` can outlive the entry it points at (server clamps to 10
 * FIFO), so the index is clamped here the same way ShotCard clamps it.
 */
function resolveFrame(frame: {
    t2i_image_urls?: string[];
    t2i_selected_index?: number;
    rendered_image_url?: string;
    image_url?: string;
}) {
    const candidates = Array.isArray(frame.t2i_image_urls) ? frame.t2i_image_urls : [];
    if (candidates.length > 0) {
        const raw = typeof frame.t2i_selected_index === "number" ? frame.t2i_selected_index : 0;
        const index = Math.max(0, Math.min(raw, candidates.length - 1));
        return media(candidates[index]);
    }
    return media(frame.rendered_image_url || frame.image_url);
}

export function resolveAssetMedia(asset: unknown, kind: AssetKind): ResolvedMedia | null {
    if (!asset || typeof asset !== "object") return null;

    switch (kind) {
        case "character":
            return media(characterImageUrl(asset as Character));
        case "scene":
        case "prop":
            return resolveImageAssetHolder(asset as Parameters<typeof resolveImageAssetHolder>[0]);
        case "frame":
            return resolveFrame(asset as Parameters<typeof resolveFrame>[0]);
        case "generation":
            return media((asset as { media_path?: string }).media_path);
        default:
            return null;
    }
}

/** Same source-of-truth as resolveAssetMedia, but returns the full selected
 *  variant (for has_grid_overlay etc) instead of just a display path. Frame
 *  and generation kinds don't carry variant history, so they return undefined. */
export function resolveAssetVariant(asset: unknown, kind: AssetKind): ImageVariant | undefined {
    if (!asset || typeof asset !== "object") return undefined;

    switch (kind) {
        case "character":
            return characterSelectedVariant(asset as Character);
        case "scene":
        case "prop":
            return selectedVariant((asset as { image_asset?: ImageAsset }).image_asset);
        default:
            return undefined;
    }
}
