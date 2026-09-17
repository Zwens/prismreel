/**
 * 分鏡提示詞的可插入預設：運鏡 + 動作/姿勢。
 *
 * 兩類的插入形式不同，這是有原因的：
 * - 運鏡插 `(camera: ...)`，因為後端要把它解析成 camera_movement_description 字段
 *   （見 StoryboardR2V.tsx 的 field === "cameraMovement" 分支）。
 * - 動作/姿勢插純文本，因為它本來就是分鏡描述的一部分，沒有任何消費方需要
 *   把它和其餘描述區分開。包一層標記只會增加 PromptBuilder 的解析負擔。
 */

export type InsertMode = "camera" | "text";

export interface ShotPresetOption {
    /** 顯示文案，雙語，與既有運鏡選項的寫法保持一致 */
    label: string;
    /** 插入到提示詞裡的英文描述 */
    value: string;
}

export interface ShotPresetGroup {
    label: string;
    options: ShotPresetOption[];
}

/** 運鏡。原先定義在 PromptBuilder.tsx 裡但從未被渲染，這裡救活。 */
export const CAMERA_GROUPS: ShotPresetGroup[] = [
    {
        label: "Basic Movement (基礎運鏡)",
        options: [
            { label: "⬅️ 水平左移 (Pan Left)", value: "camera pans left" },
            { label: "➡️ 水平右移 (Pan Right)", value: "camera pans right" },
            { label: "⬆️ 向上推移 (Tilt Up)", value: "camera pans up" },
            { label: "⬇️ 向下推移 (Tilt Down)", value: "camera pans down" },
            { label: "🔍+ 鏡頭推進 (Zoom In)", value: "zoom in, close up" },
            { label: "🔍- 鏡頭拉遠 (Zoom Out)", value: "zoom out, wide angle" },
        ],
    },
    {
        label: "Cinematic (高級/電影感運鏡)",
        options: [
            { label: "🔄 環繞拍攝 (Orbit)", value: "camera orbits around, 360 degree view" },
            { label: "👀 第一人稱 (FPV)", value: "FPV view, first person perspective" },
            { label: "✈️ 無人機航拍 (Drone)", value: "drone shot, aerial view, fly over" },
            { label: "🎦 手持晃動 (Handheld)", value: "handheld camera, shaky cam, realistic" },
            { label: "🏃 跟隨運鏡 (Tracking)", value: "tracking shot, following the subject" },
            { label: "📍 固定機位 (Static)", value: "static camera, no movement, tripod shot" },
        ],
    },
];

/** 動作與姿勢。短視頻常見的變裝、舞蹈、經典姿勢與情感互動。 */
export const ACTION_GROUPS: ShotPresetGroup[] = [
    {
        label: "Transformation (變裝)",
        options: [
            {
                label: "✨ 光效變身",
                value: "she spins in place as ribbons of light wrap around her, her outfit dissolving and reforming in a burst of sparkles",
            },
            {
                label: "⚡ 換裝閃切",
                value: "a bright flash sweeps the frame and her outfit is instantly replaced with a different one, same pose held throughout",
            },
            {
                label: "🎴 二次元化",
                value: "the figure transforms into an anime character, cel-shaded outlines sweeping across the body from head to toe",
            },
            {
                label: "💠 破碎重組",
                value: "her clothing shatters into glowing fragments that swirl around her and reassemble into a new costume",
            },
        ],
    },
    {
        label: "Dance (舞蹈)",
        options: [
            {
                label: "🙌 手勢舞",
                value: "performing a rhythmic hand-gesture dance on the beat, framed from the waist up",
            },
            {
                label: "💃 全身熱舞",
                value: "energetic full-body dance, shoulders and hips moving to the rhythm, full shot",
            },
            {
                label: "👯 雙人配合舞",
                value: "two dancers moving in synchronized choreography, mirrored steps in perfect time",
            },
            {
                label: "🌀 慢動作旋轉",
                value: "slow-motion spin, skirt and hair flaring outward, weightless and fluid",
            },
        ],
    },
    {
        label: "Iconic Pose (經典姿勢)",
        options: [
            {
                label: "👀 回眸",
                value: "turning to look back over one shoulder, hair sweeping with the motion",
            },
            {
                label: "🤗 托腮",
                value: "resting chin on one hand, gazing softly toward the camera",
            },
            {
                label: "🫰 雙手比心",
                value: "forming a heart shape with both hands, smiling at the camera",
            },
            {
                label: "🔙 背身回首",
                value: "seen from behind, then glancing back toward the camera",
            },
            {
                label: "🌬️ 仰頭閉眼",
                value: "head tilted back, eyes closed, wind moving through the hair",
            },
            {
                label: "⚔️ 戰鬥起手式",
                value: "settling into a ready combat stance, weapon raised, weight low",
            },
        ],
    },
    {
        label: "Romance Beat (情感互動)",
        options: [
            {
                label: "💗 額頭相抵",
                value: "the two lean close until their foreheads touch, eyes lowered",
            },
            {
                label: "😚 輕吻",
                value: "a soft, brief kiss",
            },
            {
                label: "🫂 擁抱",
                value: "pulling each other into a warm, unhurried embrace",
            },
            {
                label: "🤝 十指相扣",
                value: "their hands come together, fingers interlacing",
            },
        ],
    },
];
