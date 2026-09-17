"use client";
/**
 * GridOverlayPicker — 照片上傳前的網格疊加三選一（原圖 / 4x4 / 5x5）。
 *
 * 後端 `apply_grid_overlay` 會把網格線永久燒進照片本體（不可逆），
 * 所有 6 個照片上傳入口共用同一份文案，避免各處措辭漂移。
 */
import clsx from "clsx";

export type GridOverlaySize = 0 | 4 | 5;

export interface GridOverlayPickerProps {
    value: GridOverlaySize;
    onChange: (value: GridOverlaySize) => void;
    className?: string;
}

const OPTIONS: { value: GridOverlaySize; label: string }[] = [
    { value: 0, label: "原圖" },
    { value: 4, label: "4×4 網格" },
    { value: 5, label: "5×5 網格" },
];

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
