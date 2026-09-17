// Prompt builders for the dance-swap flow.
//
// These are deliberately in one file and deliberately verbose: the wording here
// is the single biggest lever on output quality, and it was arrived at by
// measurement rather than taste (see
// docs/superpowers/specs/2026-09-15-real-person-dance-spike.md).

/** Realism levels for the character sheet.
 *
 * `photoreal` produces the best-looking sheet but Ark rejects it as a
 * reference image (`InputImageSensitiveContentDetected.PrivacyInformation`) —
 * it is offered because the sheet is still useful on its own, and because the
 * user should see the rejection rather than have us quietly downgrade them.
 *
 * `illustration` is the most realistic level that Ark actually accepts.
 * Verified: a sheet asked for as "3D CG game character" came back with
 * photographic skin and was rejected, while one asked for as a painted
 * illustration passed. The line is whether it reads as a photograph, not how
 * stylised it claims to be — so the illustration prompt says so explicitly.
 */
export type SheetStyle = 'photoreal' | 'illustration' | 'anime';

const STYLE_CLAUSE: Record<SheetStyle, string> = {
  photoreal:
    'Photorealistic studio photography, natural skin texture and real hair strands.',
  illustration:
    'Rendered as a hand-painted semi-realistic illustration with visible line work ' +
    'and flat shading. It must clearly read as a drawing, not as a photograph — ' +
    'no photographic skin pores, no photographic hair strands.',
  anime:
    'Rendered as a clean modern 2D anime character sheet, cel shading, flat colours, ' +
    'stylised anime face.',
};

export function buildThreeViewPrompt(outfit: string, style: SheetStyle, hasGridOverlay = false): string {
  const outfitClause = outfit.trim()
    ? `Change the outfit to: ${outfit.trim()}.`
    : 'Keep the outfit from the reference image.';

  const gridClause = hasGridOverlay
    ? 'The reference image has a proportion grid overlaid on it to help you ' +
      'read body proportions and composition accurately. Use the grid only as ' +
      'a measurement guide — do not reproduce the grid lines in the output.'
    : '';

  return [
    'Using the person in the reference image as the exact same character',
    '(same face, same hair, same body proportions), produce a character',
    'three-view turnaround sheet: front view, side view (90 degrees), and back',
    'view, standing in a neutral A-pose, evenly spaced left to right in a single',
    'image, full body head to toe in all three views, consistent scale and',
    'eye-line across the three views.',
    outfitClause,
    'Plain pure white background, flat even lighting, no shadows, no text.',
    STYLE_CLAUSE[style],
    gridClause,
  ].filter(Boolean).join(' ');
}

/** The final compose prompt.
 *
 * Two clauses here are load-bearing and should not be dropped when editing:
 *
 *  - naming the reference video as a *depth* reference, and
 *  - "Do not render the depth map itself"
 *
 * Without them the model sometimes treats the grayscale input as the desired
 * look and returns a grey clip rather than a full-colour character.
 */
export function buildComposePrompt(opts: {
  outfit: string;
  scene: string;
  hasSheet: boolean;
}): string {
  const subject = opts.hasSheet
    ? 'The character shown in the reference image'
    : 'The person in the reference video';

  const outfitClause = opts.outfit.trim()
    ? `Keep her face and hair unchanged, and dress her in ${opts.outfit.trim()}.`
    : 'Keep her face, hair and outfit exactly as in the reference.';

  const scene = opts.scene.trim()
    ? opts.scene.trim()
    : 'a bright empty dance studio with a wooden floor';

  return [
    `${subject} performs the exact dance motion of the black-and-white depth`,
    'reference video — identical choreography, identical timing, identical body',
    'movement.',
    outfitClause,
    `Render her as a full-colour character in ${scene}, static locked-off camera,`,
    'full body in frame.',
    'Do not render the depth map itself.',
  ].join(' ');
}

/** Prompt for the no-sheet path: the reference clip is the source of truth. */
export function buildOutfitOnlyPrompt(opts: { outfit: string; scene: string }): string {
  const outfitClause = opts.outfit.trim()
    ? `change her outfit to ${opts.outfit.trim()}`
    : 'keep her outfit as it is';
  const sceneClause = opts.scene.trim() ? `, and set the scene in ${opts.scene.trim()}` : '';

  return (
    'Keep the exact same dance, the same person, the same camera and framing, ' +
    `but ${outfitClause}${sceneClause}.`
  );
}
