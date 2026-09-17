"use client";
/**
 * GridOverlayPicker — 照片上传前的网格叠加三选一（原图 / 4x4 / 5x5）。
 *
 * 后端 `apply_grid_overlay` 会把网格线永久烧进照片本体（不可逆），
 * 所有 6 个照片上传入口共用同一份文案，避免各处措辞漂移。
 */
import clsx from "clsx";

export type GridOverlaySize = 0 | 4 | 5;

export interface GridOverlayPickerProps {
    value: GridOverlaySize;
    onChange: (value: GridOverlaySize) => void;
    className?: string;
}

const OPTIONS: { value: GridOverlaySize; label: string }[] = [
    { value: 0, label: "原图" },
    { value: 4, label: "4×4 网格" },
    { value: 5, label: "5×5 网格" },
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
                真人照片建议使用网格叠加，辅助 AI 识别人物比例与构图。
            </p>
            <p className="text-[0.6875rem] leading-snug text-amber-500/90">
                网格叠加会永久修改照片，请自行保留原图备份。
            </p>
        </div>
    );
}
