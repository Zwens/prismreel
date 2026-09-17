/**
 * Resolve a storyboard frame's linked assets into R2V reference image slots.
 *
 * Every frame carries character_ids / scene_id / prop_ids, so the slots can be
 * filled by exact id lookup — no guessing names out of the prose description.
 * Order is characters → scene → props because character1 is the R2V slot the
 * model treats as the subject.
 */

export interface ReferenceSlot {
    url: string;
    name: string;
}

export interface FrameReferenceSlots {
    slots: ReferenceSlot[];
    /** Linked assets that have no reference image yet — generate them first. */
    missing: string[];
    /** Linked assets dropped because the model's slot budget ran out. */
    truncated: string[];
}

/** Character reference image, new schema first, legacy fields as fallback.
 *  Mirrors resolveCharacterImage in Cast so both views agree on which image
 *  represents a character. */
function characterImage(c: any): string | undefined {
    const sheet = c?.reference_sheet;
    const sheetUrl = sheet?.image_variants?.find(
        (v: any) => v.id === sheet.selected_image_id,
    )?.url;
    if (sheetUrl) return sheetUrl;

    const fullBody = c?.full_body;
    const fullBodyUrl = fullBody?.image_variants?.find(
        (v: any) => v.id === fullBody.selected_image_id,
    )?.url;
    if (fullBodyUrl) return fullBodyUrl;

    return c?.full_body_image_url
        || c?.three_view_image_url
        || c?.headshot_image_url
        || c?.image_url;
}

function simpleImage(entity: any): string | undefined {
    return entity?.image_url || entity?.reference_image_url;
}

interface AssetPools {
    characters?: any[];
    scenes?: any[];
    props?: any[];
}

/** A frame's linked assets in slot order, deduped.
 *
 * Characters first because character1 is the slot R2V treats as the subject;
 * a frame can list the same character twice and one reference is enough.
 */
function linkedEntities(frame: any, project: AssetPools): Array<{ entity: any; url?: string }> {
    const characters = project?.characters ?? [];
    const scenes = project?.scenes ?? [];
    const props = project?.props ?? [];

    const linked: Array<{ entity: any; url?: string }> = [];
    const seen = new Set<string>();

    const push = (entity: any, url?: string) => {
        if (!entity || seen.has(entity.id)) return;
        seen.add(entity.id);
        linked.push({ entity, url });
    };

    for (const id of frame?.character_ids ?? []) {
        const c = characters.find((e: any) => e.id === id);
        if (c) push(c, characterImage(c));
    }
    if (frame?.scene_id) {
        const s = scenes.find((e: any) => e.id === frame.scene_id);
        if (s) push(s, simpleImage(s));
    }
    for (const id of frame?.prop_ids ?? []) {
        const p = props.find((e: any) => e.id === id);
        if (p) push(p, simpleImage(p));
    }

    return linked;
}

/** Names of everything a frame links to, in slot order.
 *
 * Includes assets that have no reference image yet: writing the tag declares
 * the intent, and generation already refuses with a clear "尚未生成圖片"
 * message. Omitting them would silently drop the reference instead.
 */
export function frameLinkedAssetNames(frame: any, project: AssetPools): string[] {
    return linkedEntities(frame, project).map(({ entity }) => entity.name);
}

export function resolveFrameReferenceSlots(
    frame: any,
    project: AssetPools,
    maxSlots: number,
): FrameReferenceSlots {
    const linked = linkedEntities(frame, project);

    const slots: ReferenceSlot[] = [];
    const missing: string[] = [];
    const truncated: string[] = [];

    for (const { entity, url } of linked) {
        if (!url) {
            missing.push(entity.name);
            continue;
        }
        if (slots.length >= maxSlots) {
            truncated.push(entity.name);
            continue;
        }
        slots.push({ url, name: entity.name });
    }

    return { slots, missing, truncated };
}
