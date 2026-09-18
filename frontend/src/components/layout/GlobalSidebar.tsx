"use client";

import { LayoutGrid, Layers, Clapperboard, ImagePlus, Clock, Settings, LogOut, Gauge } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import PrismReelBranding from "./PrismReelBranding";
import { logout } from "@/lib/api";

export type GlobalTab = "workspace" | "library" | "videogen" | "imagegen" | "history" | "settings";

interface GlobalSidebarProps {
  activeTab: GlobalTab;
  onTabChange: (tab: GlobalTab) => void;
}

// Shared global nav model (workspace/library/videogen/imagegen/history + settings).
// Reused by the desktop GlobalSidebar (below) and the mobile BottomTabBar (md:hidden).
// videogen/imagegen replace the former single "playground" entry + the standalone
// "aivideo" quick-start page — both folded into videogen's mode tabs (2026-09-18).
export const GLOBAL_NAV_ITEMS: { id: GlobalTab; icon: typeof LayoutGrid; hash: string }[] = [
  { id: "workspace", icon: LayoutGrid, hash: "#/" },
  { id: "videogen", icon: Clapperboard, hash: "#/video-gen" },
  { id: "imagegen", icon: ImagePlus, hash: "#/image-gen" },
  { id: "library", icon: Layers, hash: "#/library" },
  { id: "history", icon: Clock, hash: "#/history" },
  { id: "settings", icon: Settings, hash: "#/settings" },
];

const APP_VERSION = "v1.5.0";

function NavButton({
  active,
  label,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: typeof LayoutGrid;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "group relative flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-left transition-colors",
        active
          ? "bg-primary/10 text-foreground font-semibold"
          : "text-text-secondary hover:bg-hover-bg hover:text-foreground font-medium"
      )}
    >
      {/* Active accent bar */}
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-[18px] w-[3px] rounded-r bg-primary" />
      )}
      <Icon
        size={18}
        strokeWidth={1.8}
        className={clsx(
          "flex-shrink-0 transition-colors",
          active ? "text-primary" : "text-text-muted group-hover:text-foreground"
        )}
      />
      <span className="text-base">{label}</span>
    </button>
  );
}

/**
 * 全局導航 —— 帶文字標籤的品牌側欄（Line B "Luminous Atelier"）。
 *
 * 頂部常駐 PRISMREEL 字標 + Slogan；主導航圖標+文字（無 hover、無歧義）；
 * 設置固定底部；底部版本號。早先為給二級篩選欄騰地的 60px 圖標軌已廢棄——
 * 資產庫/設置改走橫向篩選後，豎向只剩這一條欄，故恢復完整品牌呈現。
 * 結構對所有主題統一，視覺身份由語義 token 切換（zero-leak）。
 */
export default function GlobalSidebar({ activeTab, onTabChange }: GlobalSidebarProps) {
  const t = useTranslations("nav");
  const tUsage = useTranslations("usage");
  const router = useRouter();

  const handleNav = (id: GlobalTab, hash: string) => {
    onTabChange(id);
    window.location.hash = hash;
  };

  const handleLogout = async () => {
    await logout();
    window.location.href = "/login";
  };

  return (
    <aside className="w-52 flex-shrink-0 h-full hidden md:flex flex-col border-r border-glass-border bg-surface/60 backdrop-blur-xl">
      {/* Brand lockup — PRISMREEL 字標 + Slogan, click → workspace */}
      <button
        type="button"
        onClick={() => handleNav("workspace", "#/")}
        aria-label={t("workspaceAria")}
        className="text-left px-4 pt-5 pb-4 border-b border-glass-border hover:opacity-90 transition-opacity"
      >
        <PrismReelBranding size="md" showSlogan={false} />
        <p className="font-display atelier-display text-[0.75rem] italic text-text-muted tracking-wide leading-snug mt-2.5">
          Render Noise into Narrative
        </p>
      </button>

      {/* Primary navigation */}
      <nav className="flex-1 flex flex-col gap-0.5 p-2.5" aria-label={t("mainNavAria")}>
        {GLOBAL_NAV_ITEMS.filter((item) => item.id !== "settings").map((item) => (
          <NavButton
            key={item.id}
            active={activeTab === item.id}
            label={t(item.id)}
            icon={item.icon}
            onClick={() => handleNav(item.id, item.hash)}
          />
        ))}
      </nav>

      {/* Settings + logout pinned bottom + version */}
      <div className="p-2.5 border-t border-glass-border">
        <NavButton
          active={false}
          label={tUsage("myUsageTitle")}
          icon={Gauge}
          onClick={() => router.push("/usage")}
        />
        <NavButton
          active={activeTab === "settings"}
          label={t("settings")}
          icon={Settings}
          onClick={() => handleNav("settings", "#/settings")}
        />
        <NavButton active={false} label={t("logout")} icon={LogOut} onClick={handleLogout} />
        <div className="px-3 pt-2.5 font-mono text-[0.6875rem] tracking-wide text-text-muted">
          {APP_VERSION}
        </div>
      </div>
    </aside>
  );
}
