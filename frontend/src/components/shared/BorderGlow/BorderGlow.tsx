"use client";
/**
 * BorderGlow — React Bits 同名組件的 TS 適配版（"JavaScript + CSS" 變體）。
 *
 * 行為：hover 時根據 cursor 與卡片中心的角度 / 邊距動態點亮 conic-gradient 的
 * 邊光 + mesh-gradient 邊框。設計意圖是讓較大尺寸的 hero card / panel 在被
 * 關注時獲得"真材實料"的發光描邊，而不是簡單的 box-shadow。
 *
 * 在 PrismReel 裏的應用場景（截至 2026-05）：
 *   - PolishPanel 展開容器（首次結果完成時 sweep + hover 時 ambient glow）
 *
 * 不要用在小尺寸按鈕 / chrome 控件上 —— glow 半徑默認 40px，按鈕太小會讓
 * halo 比內容還大，反而模糊。最小推薦寬度 ≥ 240px。
 */
import { useRef, useCallback, useEffect, type CSSProperties, type ReactNode } from "react";
import "./BorderGlow.css";

interface BorderGlowProps {
    children: ReactNode;
    className?: string;
    edgeSensitivity?: number;
    /** HSL "H S L"（例如 "262 80 70"），不帶 %。 */
    glowColor?: string;
    backgroundColor?: string;
    borderRadius?: number;
    glowRadius?: number;
    glowIntensity?: number;
    coneSpread?: number;
    /** mount 時播放一次 sweep 動畫（用作"AI 生成完成"瞬間的強調）。 */
    animated?: boolean;
    /** 長度 3 的 hex 顏色數組，用於 mesh-gradient 邊框色調。 */
    colors?: [string, string, string];
    /** 內層 fill 的不透明度（0-1）。0 關閉內層填充，僅保留邊光。 */
    fillOpacity?: number;
}

function parseHSL(hslStr: string): { h: number; s: number; l: number } {
    const match = hslStr.match(/([\d.]+)\s*([\d.]+)%?\s*([\d.]+)%?/);
    if (!match) return { h: 40, s: 80, l: 80 };
    return { h: parseFloat(match[1]), s: parseFloat(match[2]), l: parseFloat(match[3]) };
}

function buildGlowVars(glowColor: string, intensity: number): Record<string, string> {
    const { h, s, l } = parseHSL(glowColor);
    const base = `${h}deg ${s}% ${l}%`;
    const opacities = [100, 60, 50, 40, 30, 20, 10];
    const keys = ["", "-60", "-50", "-40", "-30", "-20", "-10"];
    const vars: Record<string, string> = {};
    for (let i = 0; i < opacities.length; i++) {
        vars[`--glow-color${keys[i]}`] = `hsl(${base} / ${Math.min(opacities[i] * intensity, 100)}%)`;
    }
    return vars;
}

const GRADIENT_POSITIONS = ["80% 55%", "69% 34%", "8% 6%", "41% 38%", "86% 85%", "82% 18%", "51% 4%"];
const GRADIENT_KEYS = [
    "--gradient-one", "--gradient-two", "--gradient-three", "--gradient-four",
    "--gradient-five", "--gradient-six", "--gradient-seven",
];
const COLOR_MAP = [0, 1, 2, 0, 1, 2, 1];

function buildGradientVars(colors: [string, string, string]): Record<string, string> {
    const vars: Record<string, string> = {};
    for (let i = 0; i < 7; i++) {
        const c = colors[Math.min(COLOR_MAP[i], colors.length - 1)];
        vars[GRADIENT_KEYS[i]] = `radial-gradient(at ${GRADIENT_POSITIONS[i]}, ${c} 0px, transparent 50%)`;
    }
    vars["--gradient-base"] = `linear-gradient(${colors[0]} 0 100%)`;
    return vars;
}

const easeOutCubic = (x: number) => 1 - Math.pow(1 - x, 3);
const easeInCubic = (x: number) => x * x * x;

interface AnimateOpts {
    start?: number;
    end?: number;
    duration?: number;
    delay?: number;
    ease?: (x: number) => number;
    onUpdate: (v: number) => void;
    onEnd?: () => void;
}

function animateValue({
    start = 0, end = 100, duration = 1000, delay = 0, ease = easeOutCubic, onUpdate, onEnd,
}: AnimateOpts): void {
    const t0 = performance.now() + delay;
    const tick = () => {
        const elapsed = performance.now() - t0;
        const t = Math.min(elapsed / duration, 1);
        onUpdate(start + (end - start) * ease(t));
        if (t < 1) requestAnimationFrame(tick);
        else if (onEnd) onEnd();
    };
    setTimeout(() => requestAnimationFrame(tick), delay);
}

export default function BorderGlow({
    children,
    className = "",
    edgeSensitivity = 30,
    glowColor = "262 80 70",
    backgroundColor = "rgba(20, 17, 31, 0.92)",
    borderRadius = 12,
    glowRadius = 32,
    glowIntensity = 0.85,
    coneSpread = 25,
    animated = false,
    colors = ["#646cff", "#a855f7", "#ec4899"],
    fillOpacity = 0.35,
}: BorderGlowProps) {
    const cardRef = useRef<HTMLDivElement | null>(null);

    const getCenter = useCallback((el: HTMLDivElement) => {
        const { width, height } = el.getBoundingClientRect();
        return [width / 2, height / 2] as const;
    }, []);

    const getEdgeProximity = useCallback((el: HTMLDivElement, x: number, y: number) => {
        const [cx, cy] = getCenter(el);
        const dx = x - cx;
        const dy = y - cy;
        let kx = Infinity;
        let ky = Infinity;
        if (dx !== 0) kx = cx / Math.abs(dx);
        if (dy !== 0) ky = cy / Math.abs(dy);
        return Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);
    }, [getCenter]);

    const getCursorAngle = useCallback((el: HTMLDivElement, x: number, y: number) => {
        const [cx, cy] = getCenter(el);
        const dx = x - cx;
        const dy = y - cy;
        if (dx === 0 && dy === 0) return 0;
        const radians = Math.atan2(dy, dx);
        let degrees = radians * (180 / Math.PI) + 90;
        if (degrees < 0) degrees += 360;
        return degrees;
    }, [getCenter]);

    const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
        const card = cardRef.current;
        if (!card) return;
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const edge = getEdgeProximity(card, x, y);
        const angle = getCursorAngle(card, x, y);
        card.style.setProperty("--edge-proximity", `${(edge * 100).toFixed(3)}`);
        card.style.setProperty("--cursor-angle", `${angle.toFixed(3)}deg`);
    }, [getEdgeProximity, getCursorAngle]);

    useEffect(() => {
        if (!animated || !cardRef.current) return;
        const card = cardRef.current;
        const angleStart = 110;
        const angleEnd = 465;
        card.classList.add("sweep-active");
        card.style.setProperty("--cursor-angle", `${angleStart}deg`);

        animateValue({ duration: 500, onUpdate: (v) => card.style.setProperty("--edge-proximity", String(v)) });
        animateValue({
            ease: easeInCubic, duration: 1500, end: 50,
            onUpdate: (v) => card.style.setProperty("--cursor-angle", `${(angleEnd - angleStart) * (v / 100) + angleStart}deg`),
        });
        animateValue({
            ease: easeOutCubic, delay: 1500, duration: 2250, start: 50, end: 100,
            onUpdate: (v) => card.style.setProperty("--cursor-angle", `${(angleEnd - angleStart) * (v / 100) + angleStart}deg`),
        });
        animateValue({
            ease: easeInCubic, delay: 2500, duration: 1500, start: 100, end: 0,
            onUpdate: (v) => card.style.setProperty("--edge-proximity", String(v)),
            onEnd: () => card.classList.remove("sweep-active"),
        });
    }, [animated]);

    const glowVars = buildGlowVars(glowColor, glowIntensity);
    const gradientVars = buildGradientVars(colors);

    const styleVars = {
        "--card-bg": backgroundColor,
        "--edge-sensitivity": edgeSensitivity,
        "--border-radius": `${borderRadius}px`,
        "--glow-padding": `${glowRadius}px`,
        "--cone-spread": coneSpread,
        "--fill-opacity": fillOpacity,
        ...glowVars,
        ...gradientVars,
    } as CSSProperties;

    return (
        <div
            ref={cardRef}
            onPointerMove={handlePointerMove}
            className={`border-glow-card ${className}`}
            style={styleVars}
        >
            <span className="edge-light" />
            <div className="border-glow-inner">{children}</div>
        </div>
    );
}
