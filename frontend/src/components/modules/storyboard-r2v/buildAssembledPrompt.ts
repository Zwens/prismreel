import type { ShotNode } from "./ShotCard";

/**
 * Real-time compute the final assembled prompt from the user's textarea
 * (visual narrative) + structured fields (camera language metadata).
 *
 * Rules (grill-me 2026-05-28, corrected):
 * - duration → NOT in prompt (唯一的特殊字段，走 API `duration` 參數)
 * - shot_size + camera_angle → appended to prompt tail
 * - camera_movement → appended to prompt tail (自然語言描述，含速度)
 * - transition_hint → appended to prompt tail (可選，多分鏡視頻內轉場)
 *
 * Final = textarea visual narrative + 運鏡 + 景別/機位 + 轉場
 */
export function buildAssembledPrompt(shot: ShotNode): string {
    let base = (shot.prompt || "").trim();

    // Strip existing reference tags from the display — they're handled
    // separately as reference_image URLs in the API call
    base = base.replace(/\[character\d+:[^\]]+\]/g, "").replace(/\s+/g, " ").trim();

    const suffixes: string[] = [];

    // Camera movement (natural language, speed naturally embedded)
    if (shot.cameraMovementStructured) {
        const desc = shot.cameraMovementStructured.description || shot.cameraMovementStructured.primary;
        if (desc) suffixes.push(desc);
    }

    // Shot size + camera angle (grouped)
    const framingParts: string[] = [];
    if (shot.shotSize) framingParts.push(shot.shotSize);
    if (shot.cameraAngle) framingParts.push(shot.cameraAngle);
    if (framingParts.length > 0) {
        suffixes.push(framingParts.join("，"));
    }

    // Transition hint (optional, for multi-shot internal transitions)
    if (shot.transitionHint) {
        suffixes.push(shot.transitionHint);
    }

    if (suffixes.length === 0) return base;

    const separator = base.endsWith("。") || base.endsWith(".") || base.endsWith("，") || base.endsWith(",")
        ? ""
        : "，";
    return base + separator + suffixes.join("，");
}
