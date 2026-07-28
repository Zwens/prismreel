/**
 * 分镜提示词的可插入预设：运镜 + 动作/姿势。
 *
 * 两类的插入形式不同，这是有原因的：
 * - 运镜插 `(camera: ...)`，因为后端要把它解析成 camera_movement_description 字段
 *   （见 StoryboardR2V.tsx 的 field === "cameraMovement" 分支）。
 * - 动作/姿势插纯文本，因为它本来就是分镜描述的一部分，没有任何消费方需要
 *   把它和其余描述区分开。包一层标记只会增加 PromptBuilder 的解析负担。
 */

export type InsertMode = "camera" | "text";

export interface ShotPresetOption {
    /** 显示文案，双语，与既有运镜选项的写法保持一致 */
    label: string;
    /** 插入到提示词里的英文描述 */
    value: string;
}

export interface ShotPresetGroup {
    label: string;
    options: ShotPresetOption[];
}

/** 运镜。原先定义在 PromptBuilder.tsx 里但从未被渲染，这里救活。 */
export const CAMERA_GROUPS: ShotPresetGroup[] = [
    {
        label: "Basic Movement (基础运镜)",
        options: [
            { label: "⬅️ 水平左移 (Pan Left)", value: "camera pans left" },
            { label: "➡️ 水平右移 (Pan Right)", value: "camera pans right" },
            { label: "⬆️ 向上推移 (Tilt Up)", value: "camera pans up" },
            { label: "⬇️ 向下推移 (Tilt Down)", value: "camera pans down" },
            { label: "🔍+ 镜头推进 (Zoom In)", value: "zoom in, close up" },
            { label: "🔍- 镜头拉远 (Zoom Out)", value: "zoom out, wide angle" },
        ],
    },
    {
        label: "Cinematic (高级/电影感运镜)",
        options: [
            { label: "🔄 环绕拍摄 (Orbit)", value: "camera orbits around, 360 degree view" },
            { label: "👀 第一人称 (FPV)", value: "FPV view, first person perspective" },
            { label: "✈️ 无人机航拍 (Drone)", value: "drone shot, aerial view, fly over" },
            { label: "🎦 手持晃动 (Handheld)", value: "handheld camera, shaky cam, realistic" },
            { label: "🏃 跟随运镜 (Tracking)", value: "tracking shot, following the subject" },
            { label: "📍 固定机位 (Static)", value: "static camera, no movement, tripod shot" },
        ],
    },
];

/** 动作与姿势。短视频常见的变装、舞蹈、经典姿势与情感互动。 */
export const ACTION_GROUPS: ShotPresetGroup[] = [
    {
        label: "Transformation (变装)",
        options: [
            {
                label: "✨ 光效变身",
                value: "she spins in place as ribbons of light wrap around her, her outfit dissolving and reforming in a burst of sparkles",
            },
            {
                label: "⚡ 换装闪切",
                value: "a bright flash sweeps the frame and her outfit is instantly replaced with a different one, same pose held throughout",
            },
            {
                label: "🎴 二次元化",
                value: "the figure transforms into an anime character, cel-shaded outlines sweeping across the body from head to toe",
            },
            {
                label: "💠 破碎重组",
                value: "her clothing shatters into glowing fragments that swirl around her and reassemble into a new costume",
            },
        ],
    },
    {
        label: "Dance (舞蹈)",
        options: [
            {
                label: "🙌 手势舞",
                value: "performing a rhythmic hand-gesture dance on the beat, framed from the waist up",
            },
            {
                label: "💃 全身热舞",
                value: "energetic full-body dance, shoulders and hips moving to the rhythm, full shot",
            },
            {
                label: "👯 双人配合舞",
                value: "two dancers moving in synchronized choreography, mirrored steps in perfect time",
            },
            {
                label: "🌀 慢动作旋转",
                value: "slow-motion spin, skirt and hair flaring outward, weightless and fluid",
            },
        ],
    },
    {
        label: "Iconic Pose (经典姿势)",
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
                label: "🫰 双手比心",
                value: "forming a heart shape with both hands, smiling at the camera",
            },
            {
                label: "🔙 背身回首",
                value: "seen from behind, then glancing back toward the camera",
            },
            {
                label: "🌬️ 仰头闭眼",
                value: "head tilted back, eyes closed, wind moving through the hair",
            },
            {
                label: "⚔️ 战斗起手式",
                value: "settling into a ready combat stance, weapon raised, weight low",
            },
        ],
    },
    {
        label: "Romance Beat (情感互动)",
        options: [
            {
                label: "💗 额头相抵",
                value: "the two lean close until their foreheads touch, eyes lowered",
            },
            {
                label: "😚 轻吻",
                value: "a soft, brief kiss",
            },
            {
                label: "🫂 拥抱",
                value: "pulling each other into a warm, unhurried embrace",
            },
            {
                label: "🤝 十指相扣",
                value: "their hands come together, fingers interlacing",
            },
        ],
    },
];
