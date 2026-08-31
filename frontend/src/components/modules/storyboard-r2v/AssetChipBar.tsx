"use client";

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

interface AssetChipBarProps {
    characters: any[];
    scenes: any[];
    props: any[];
    onInsertAsset: (type: string, name: string) => void;
    /** Names already tagged in this shot's prompt — shown as selected so the
     *  bar reads as "what this shot uses", not just "what exists". */
    referencedNames?: readonly string[];
}

export default function AssetChipBar({
    characters,
    scenes,
    props,
    onInsertAsset,
    referencedNames = [],
}: AssetChipBarProps) {
    const t = useTranslations("storyboardR2V");

    if (characters.length === 0 && scenes.length === 0 && props.length === 0) {
        return null;
    }

    const referenced = new Set(referencedNames);

    const chip = (asset: any, type: string, dotClass: string) => {
        const isOn = referenced.has(asset.name);
        return (
            <button
                key={asset.id}
                onClick={() => onInsertAsset(type, asset.name)}
                title={isOn ? t("chipReferenced") : undefined}
                className={
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] max-w-[200px] transition-colors duration-fast ease-out-quart "
                    + (isOn
                        ? "border-primary/45 bg-primary/10 text-foreground"
                        : "border-glass-border bg-surface-inset text-text-secondary hover:bg-hover-bg hover:text-foreground")
                }
            >
                {isOn
                    ? <Check size={11} strokeWidth={2.5} className="shrink-0 text-primary" />
                    : <span className={`h-[6px] w-[6px] shrink-0 rounded-full ${dotClass}`} />}
                <span className="truncate">{asset.name}</span>
            </button>
        );
    };

    return (
        <div className="flex flex-wrap items-center gap-2 py-1">
            {characters.map((c: any) => chip(c, "character", "bg-blue-400"))}
            {scenes.map((s: any) => chip(s, "scene", "bg-teal-400"))}
            {props.map((p: any) => chip(p, "prop", "bg-orange-400"))}
        </div>
    );
}
