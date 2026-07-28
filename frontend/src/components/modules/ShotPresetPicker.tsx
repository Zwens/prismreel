"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import type { ShotPresetGroup } from "./shotPresets";

interface ShotPresetPickerProps {
    label: string;
    icon: React.ReactNode;
    groups: ShotPresetGroup[];
    /** 传入选项的 value，由调用方决定包装成什么形式插入 */
    onPick: (value: string) => void;
}

/**
 * 分组下拉，用于把预设的运镜/动作插入提示词。
 *
 * 选完即关闭——这些选项是往提示词里追加文本，不是互斥的单选状态，
 * 所以不保留选中态，连续插两个就点两次。
 */
const ShotPresetPicker: React.FC<ShotPresetPickerProps> = ({ label, icon, groups, onPick }) => {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;

        const onPointerDown = (e: MouseEvent) => {
            if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setOpen(false);
        };

        document.addEventListener("mousedown", onPointerDown);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("mousedown", onPointerDown);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [open]);

    return (
        <div className="relative" ref={rootRef}>
            <button
                type="button"
                onClick={() => setOpen(o => !o)}
                aria-haspopup="listbox"
                aria-expanded={open}
                className={`text-xs flex items-center gap-1 px-2 py-1 rounded transition-colors ${open
                    ? "text-foreground bg-glass"
                    : "text-text-secondary hover:text-foreground hover:bg-glass"
                    }`}
            >
                {icon} {label}
                <ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
            </button>

            {open && (
                <div
                    role="listbox"
                    className="absolute right-0 top-full mt-1 z-50 w-64 max-h-80 overflow-y-auto rounded-lg border border-glass-border bg-elevated shadow-xl py-1"
                >
                    {groups.map(group => (
                        <div key={group.label}>
                            <div className="px-3 py-1.5 text-[0.625rem] uppercase tracking-wider text-text-muted">
                                {group.label}
                            </div>
                            {group.options.map(option => (
                                <button
                                    key={option.value}
                                    type="button"
                                    role="option"
                                    aria-selected={false}
                                    title={option.value}
                                    onClick={() => {
                                        onPick(option.value);
                                        setOpen(false);
                                    }}
                                    className="w-full text-left px-3 py-1.5 text-xs text-text-secondary hover:text-foreground hover:bg-glass transition-colors"
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default ShotPresetPicker;
