import type { Character, ImageAsset, ImageVariant, AssetUnit } from "@/store/projectStore";

/**
 * Character image resolution helpers.
 *
 * Characters store images in two containers from two schema eras:
 *   - reference_sheet (new, canonical): { image_variants, selected_image_id }
 *   - full_body_asset (legacy):         { variants, selected_id }
 *
 * New characters are written to reference_sheet only, so every consumer must
 * read reference_sheet first and fall back to full_body_asset — otherwise newly
 * generated characters render blank. Centralised here so call sites can't drift.
 *
 * NOTE: this is for resolving a character's *display / reference* image. It is
 * NOT for full_body-specific management UI (e.g. CharacterWorkbench panels that
 * edit the full_body asset type itself).
 */

/** Selected (or first) variant from EITHER container shape, full object. */
export function selectedVariant(asset?: ImageAsset | AssetUnit | null): ImageVariant | undefined {
  if (!asset) return undefined;
  const variants = "image_variants" in asset ? asset.image_variants : asset.variants;
  if (!variants?.length) return undefined;
  const selectedId = "image_variants" in asset ? asset.selected_image_id : asset.selected_id;
  return variants.find((v) => v.id === selectedId) || variants[0];
}

/** Selected (or first) variant URL from EITHER container shape. */
export function selectedVariantUrl(asset?: ImageAsset | AssetUnit | null): string | undefined {
  return selectedVariant(asset)?.url;
}

/** Resolve a character's primary image container to a normalized ImageAsset
 *  ({ variants, selected_id }), preferring reference_sheet over legacy full_body. */
export function characterImageAsset(c: Character): ImageAsset | undefined {
  const rs = c.reference_sheet;
  if (rs?.image_variants?.length) {
    return { selected_id: rs.selected_image_id, variants: rs.image_variants };
  }
  return c.full_body_asset;
}

/** A character's variant list (reference_sheet → full_body), for counts / variant strips. */
export function characterVariants(c: Character): ImageVariant[] {
  return characterImageAsset(c)?.variants ?? [];
}

/** A character's best display image: reference_sheet → full_body → legacy top-level urls. */
export function characterImageUrl(c: Character): string | undefined {
  return selectedVariantUrl(characterImageAsset(c)) || c.image_url || c.full_body_image_url;
}

/** A character's selected variant, full object (for has_grid_overlay etc). Undefined
 *  when the character only has legacy top-level urls with no variant history. */
export function characterSelectedVariant(c: Character): ImageVariant | undefined {
  return selectedVariant(characterImageAsset(c));
}
