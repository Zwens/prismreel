"use client";
/**
 * WorkflowActionButton — R2V workflow 統一 primary action 按鈕。
 *
 * 視覺靈感：ZeroNode 項目的 frosted glass pill —— pill 形狀 + 頂部高光
 * + 半透明品牌色 + backdrop-blur，讓按鈕看起來"漂浮"在 dark glass 之上。
 *
 * 適配 PrismReel：
 *   · 用紫色 #646cff 替代藍色（與 BorderGlow / StepHeader / 整體品牌一致）
 *   · backdrop-blur 落到 PrismReel 已有的 glass 語言裏
 *   · 頂部 inset highlight 約 1px 白色 4-5% —— 極剋制，不喧賓
 *   · 三檔 variant：
 *       - primary  : 紫色填充 + 頂部高光，主行動（"應用並繼續" / "Generate ×N"）
 *       - secondary: 紫色 outline + 極淺紫填充，次行動（"導入" / "保存"）
 *       - ghost    : 透明 + 紫文字 + hover 顯玻璃，純導航（"取消" / 佔位）
 *   · loading 態：左前顯 spinner，禁交互
 *   · disabled 態：opacity 50% + cursor not-allowed
 *
 * 禁用 motion.button 包裝 —— scale-95 active 已足夠，不再加 framer-motion 重器。
 */
import { Loader2 } from "lucide-react";
import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

interface WorkflowActionButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
    /** primary = 主行動（紫色填充 frosted）
     *  secondary = 次行動（紫 outline + 極淺紫底）
     *  ghost = 純導航（透明 + hover 顯玻璃） */
    variant?: Variant;
    /** sm = 28px 高 (chrome 內嵌)；md = 36px 高（標準 step trailing）。 */
    size?: Size;
    /** 左 icon（可選）；與 children 之間有 1.5 間距。 */
    leftIcon?: ReactNode;
    /** 右 icon（可選）；常用於 ChevronRight "繼續" 暗示。 */
    rightIcon?: ReactNode;
    /** loading 時左 icon 自動換 spinner，按鈕禁用，文字不變。 */
    loading?: boolean;
    children: ReactNode;
}

/* ───────────────────────────────────────────────────────────────────
   Variant 風格表
   每檔樣式寫在這裏，避免 className 拼接裏塞條件，可讀性更好。
   ─────────────────────────────────────────────────────────────────── */
const variantStyles: Record<Variant, string> = {
    /* Primary — 實色紫 fill + frosted 頂部高光。
       v2 調整：把 frosted 從"身體半透明"挪到"頂部反射"——身體保持紫色實色
       讓對比度足夠（在 #050508 dark bg 上白字讀得清），僅頂部 1.5px 白色 14%
       inset 高光模擬"玻璃球反射"。底部加 inset 紫暗邊 + outer 紫 glow。 */
    primary: clsx(
        "text-foreground",
        "bg-primary",
        "border border-[rgba(100,108,255,0.65)]",
        "shadow-[inset_0_1.5px_0_rgba(255,255,255,0.14),inset_0_-1px_0_rgba(60,68,200,0.45),0_4px_14px_-2px_rgba(100,108,255,0.45)]",
        "hover:bg-primary-hover",
        "hover:border-[rgba(100,108,255,0.85)]",
        "hover:shadow-[inset_0_1.5px_0_rgba(255,255,255,0.20),inset_0_-1px_0_rgba(60,68,200,0.55),0_6px_18px_-2px_rgba(100,108,255,0.60)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55 focus-visible:ring-offset-2 focus-visible:ring-offset-black",
    ),
    /* Secondary — 紫 outline + 淺紫 frosted 底。
       身體仍是 frosted（10% 紫 + backdrop-blur），border 紫 40%。
       hover 加深到接近 primary 但更輕。 */
    secondary: clsx(
        "text-primary",
        "bg-[rgba(100,108,255,0.10)]",
        "border border-[rgba(100,108,255,0.40)]",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]",
        "backdrop-blur-md",
        "hover:bg-[rgba(100,108,255,0.22)] hover:border-[rgba(100,108,255,0.60)] hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55",
    ),
    /* Ghost — 透明，hover 才顯玻璃。最低權重的導航 / 取消按鈕。 */
    ghost: clsx(
        "text-text-secondary bg-transparent border border-transparent",
        "hover:bg-[rgba(255,255,255,0.06)] hover:text-foreground hover:border-glass-border",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55",
    ),
};

const sizeStyles: Record<Size, string> = {
    sm: "min-h-[30px] px-3.5 text-[0.78125rem] gap-1.5",
    md: "min-h-[38px] px-5 text-[0.8125rem] gap-2",
};

export default function WorkflowActionButton({
    variant = "primary",
    size = "md",
    leftIcon,
    rightIcon,
    loading = false,
    disabled,
    className,
    children,
    type = "button",
    ...rest
}: WorkflowActionButtonProps) {
    const isDisabled = disabled || loading;
    return (
        <button
            type={type}
            disabled={isDisabled}
            className={clsx(
                // pill — rounded-full 是核心標識，所有 variant 共享
                "inline-flex items-center justify-center rounded-full font-semibold",
                // 字體走 sans (Inter→PingFang fallback)，符合 PrismReel content tier
                "font-sans tracking-[-0.005em]",
                "select-none whitespace-nowrap",
                "transition-[background,border-color,box-shadow,transform] duration-fast ease-out-quart",
                "active:scale-[0.97]",
                "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
                sizeStyles[size],
                variantStyles[variant],
                className,
            )}
            {...rest}
        >
            {loading ? (
                <Loader2 className="animate-spin" size={size === "sm" ? 12 : 14} aria-hidden="true" />
            ) : leftIcon ? (
                <span className="grid place-items-center [&>svg]:h-3.5 [&>svg]:w-3.5">{leftIcon}</span>
            ) : null}
            <span>{children}</span>
            {rightIcon && !loading ? (
                <span className="grid place-items-center [&>svg]:h-3.5 [&>svg]:w-3.5">{rightIcon}</span>
            ) : null}
        </button>
    );
}
