/**
 * Resolution of [characterN:name] reference tags to project assets.
 *
 * The tag labels are not typed by the user — they're written by the LLM
 * that drafts and polishes each shot prompt. Despite the instruction to
 * reproduce tags verbatim, it routinely shortens the asset's real name:
 * "机械鸟" for "现代智能机械鸟", "二月红" for "二月红 (现代)". Exact
 * lookup silently dropped those references, and R2V generation then
 * refused the shot ("引用的「机械鸟」尚未生成图片") while the asset sat
 * in the cast, generated and ready.
 *
 * So: exact match first, then a UNIQUE substring match in either
 * direction. Ambiguity resolves to nothing on purpose — attaching the
 * wrong reference image is worse than telling the user to fix the tag.
 */

export interface NamedAsset {
    name?: string;
}

const norm = (s: string) => s.trim().toLowerCase();

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export interface PromptTagAugmentation {
    prompt: string;
    /** Asset names that gained a tag — empty when nothing was missing. */
    added: string[];
}

/**
 * Append the [characterN:name] tags a shot's linked assets need, leaving the
 * author's prose untouched.
 *
 * The slot number is load-bearing: slot N feeds reference_image_urls[N-1], so
 * an asset already tagged keeps its number no matter where it sits in the
 * linked list, and new assets continue past the highest number in use rather
 * than filling gaps — renumbering an existing tag would silently repoint a
 * reference image at the wrong slot.
 *
 * @param prompt      current shot prompt, authored/polished by the LLM
 * @param assetNames  linked asset names in slot-preference order
 */
export function augmentPromptWithAssetTags(
    prompt: string,
    assetNames: readonly string[],
): PromptTagAugmentation {
    const text = prompt ?? '';

    let maxSlot = 0;
    const slotRe = /\[character(\d+):([^\]]+)\]/g;
    let m: RegExpExecArray | null;
    while ((m = slotRe.exec(text)) !== null) {
        maxSlot = Math.max(maxSlot, parseInt(m[1], 10));
    }

    const additions: string[] = [];
    const added: string[] = [];
    const seen = new Set<string>();

    for (const name of assetNames) {
        if (!name || seen.has(name)) continue;
        seen.add(name);
        // Names carry parens ('张启山 (浴袍)') and slashes ('智能手环/定位玉镯');
        // escape before probing or the tag that is already there never matches.
        const present = new RegExp(`\\[character\\d+:${escapeRegExp(name)}\\]`).test(text);
        if (present) continue;
        maxSlot += 1;
        additions.push(`[character${maxSlot}:${name}]`);
        added.push(name);
    }

    if (additions.length === 0) {
        return { prompt: text, added: [] };
    }

    const joined = additions.join(' ');
    const next = text.trim() ? `${text.trimEnd()} ${joined}` : joined;
    return { prompt: next, added };
}

/**
 * Find the asset a tag label refers to.
 *
 * @param tagName label captured from [characterN:label]
 * @param pools   candidate lists in priority order (characters, scenes, props)
 */
export function resolveAssetByTagName<T extends NamedAsset>(
    tagName: string,
    pools: (readonly T[] | undefined | null)[],
): T | undefined {
    const target = norm(tagName || "");
    if (!target) return undefined;

    const lists = pools.filter(Boolean) as (readonly T[])[];

    // 1. Exact match, honouring pool priority.
    for (const list of lists) {
        const hit = list.find((a) => a?.name && norm(a.name) === target);
        if (hit) return hit;
    }

    // 2. Unique substring match across ALL pools. Scanning every pool
    //    before deciding is what makes ambiguity detectable — stopping at
    //    the first pool with a fuzzy hit would let a loose character
    //    match beat a tighter prop one.
    const fuzzy: T[] = [];
    for (const list of lists) {
        for (const a of list) {
            if (!a?.name) continue;
            const candidate = norm(a.name);
            if (candidate.includes(target) || target.includes(candidate)) {
                fuzzy.push(a);
            }
        }
    }
    return fuzzy.length === 1 ? fuzzy[0] : undefined;
}
