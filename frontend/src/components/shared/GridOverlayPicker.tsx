"use client";
/**
 * GridOverlayPicker — 照片上傳前的網格疊加三選一（原圖 / 6×6黑線 / 6×6白線）。
 *
 * 後端 `apply_grid_overlay` 會把網格線永久燒進照片本體（不可逆，固定 6×6、10px 線寬），
 * 所有上傳入口共用同一份文案，避免各處措辭漂移。
 */
import clsx from "clsx";

export type GridOverlaySize = 0 | 6;
export type GridOverlayColor = "black" | "white";
/** What the picker hands back to the caller — "none" means no grid at all. */
export type GridOverlayChoice = "none" | GridOverlayColor;

export interface GridOverlayPickerProps {
    value: GridOverlayChoice;
    onChange: (value: GridOverlayChoice) => void;
    className?: string;
}

const OPTIONS: { value: GridOverlayChoice; label: string }[] = [
    { value: "none", label: "原圖" },
    { value: "black", label: "6×6 網格（黑線）" },
    { value: "white", label: "6×6 網格（白線）" },
];

/** Translate a picker choice into the {size, color} pair the upload/apply-grid
 *  API calls take. "none" always maps to size 0 regardless of color. */
export function gridChoiceToParams(choice: GridOverlayChoice): { size: GridOverlaySize; color: GridOverlayColor } {
    return choice === "none" ? { size: 0, color: "black" } : { size: 6, color: choice };
}

export default function GridOverlayPicker({ value, onChange, className }: GridOverlayPickerProps) {
    return (
        <div className={clsx("flex flex-col gap-1.5", className)}>
            <div className="flex gap-1.5">
                {OPTIONS.map((opt) => (
                    <button
                        key={opt.value}
                        type="button"
                        onClick={() => onChange(opt.value)}
                        className={clsx(
                            "rounded-md border px-2.5 py-1 text-[0.75rem] font-medium transition-colors",
                            value === opt.value
                                ? "border-primary bg-primary/10 text-primary"
                                : "border-glass-border bg-surface text-text-muted hover:text-foreground",
                        )}
                    >
                        {opt.label}
                    </button>
                ))}
            </div>
            <p className="text-[0.6875rem] leading-snug text-text-muted">
                真人照片建議使用網格疊加，輔助 AI 識別人物比例與構圖。
            </p>
            <p className="text-[0.6875rem] leading-snug text-amber-500/90">
                網格疊加會永久修改照片，請自行保留原圖備份。
            </p>
        </div>
    );
}
