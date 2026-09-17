"use client";

/**
 * UpdateChecker — 關於頁「檢查更新」(Phase 2 設置規格 §B ⑥b)。
 *
 * 純前端、自包含、無 props：SettingsPage 直接 <UpdateChecker /> 渲染即可。
 * 手動按鈕 → 拉取 GitHub releases/latest(未授權,限流 ~60/hr)→ 與本地
 * 版本比對 → 有新版僅提示並打開發布頁(絕不自更新)。
 *
 * 主題:僅語義 token(primary=teal 動作/鏈接,accent=amber 提示),
 * 狀態文案用 text-text-secondary / text-text-muted。無硬編碼色 / 無 white-alpha。
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { RefreshCw, Loader2, Check, Sparkles, ExternalLink, CircleAlert } from "lucide-react";

// 本地版本常量,避免跨文件耦合(與 SettingsPage 的 APP_VERSION 同源)。
const APP_VERSION = "v1.5.0";
const REPO = "alibaba/prismreel";
const LATEST_API = `https://api.github.com/repos/${REPO}/releases/latest`;
const RELEASES_URL = `https://github.com/${REPO}/releases`;

type Status = "idle" | "checking" | "latest" | "update" | "error";

/** 解析為可比較的數字段:剝離前導 v,按 . + - 拆分,非數字視作 0。 */
function parseSemver(v: string): number[] {
  return v
    .trim()
    .replace(/^[vV]/, "")
    .split(/[.+-]/)
    .map((s) => {
      const n = parseInt(s, 10);
      return Number.isNaN(n) ? 0 : n;
    });
}

/** remote 是否比 current 更新(逐段數字比較,短的補 0;相等視為非更新)。 */
function isNewer(remote: string, current: string): boolean {
  const a = parseSemver(remote);
  const b = parseSemver(current);
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x > y) return true;
    if (x < y) return false;
  }
  return false;
}

export default function UpdateChecker() {
  const t = useTranslations("settings");
  const [status, setStatus] = useState<Status>("idle");
  const [remoteTag, setRemoteTag] = useState("");
  const [releaseUrl, setReleaseUrl] = useState("");
  const [errorMsg, setErrorMsg] = useState(() => t("updateError"));

  const checking = status === "checking";

  const openReleases = (url?: string) =>
    window.open(url || RELEASES_URL, "_blank", "noopener,noreferrer");

  const handleCheck = async () => {
    setStatus("checking");
    setErrorMsg(t("updateError"));
    try {
      const res = await fetch(LATEST_API, {
        headers: { Accept: "application/vnd.github+json" },
      });
      // 404 = 倉庫尚無任何 release;403 通常是未授權限流。
      if (res.status === 404) {
        setErrorMsg(t("updateNoRelease"));
        setStatus("error");
        return;
      }
      if (!res.ok) {
        setStatus("error");
        return;
      }
      const data = await res.json();
      const tag: string = typeof data?.tag_name === "string" ? data.tag_name : "";
      const url: string = typeof data?.html_url === "string" ? data.html_url : "";
      if (!tag) {
        setStatus("error");
        return;
      }
      setRemoteTag(tag);
      setReleaseUrl(url);
      setStatus(isNewer(tag, APP_VERSION) ? "update" : "latest");
    } catch {
      setStatus("error");
    }
  };

  // 狀態文案顏色:中性信息 secondary / 低調錯誤 muted / 新版用 accent(amber)。
  const statusColor =
    status === "update"
      ? "text-accent"
      : status === "error"
        ? "text-text-muted"
        : "text-text-secondary";

  const showOpenButton = status === "update" || status === "error";

  return (
    <div className="flex items-center justify-between gap-3 flex-wrap py-2.5 border-t border-glass-border text-[0.78125rem]">
      <span className="text-text-secondary shrink-0">{t("updateLabel")}</span>

      <div className="flex items-center gap-2.5 flex-wrap justify-end">
        {/* 結果區:屏幕閱讀器實時播報 */}
        <span
          role="status"
          aria-live="polite"
          className={`inline-flex items-center gap-1.5 font-mono text-[0.71875rem] ${statusColor}`}
        >
          {status === "latest" && (
            <>
              <Check size={13} />
              {t("updateUpToDate", { version: APP_VERSION })}
            </>
          )}
          {status === "update" && (
            <>
              <Sparkles size={13} />
              {t("updateNewVersion", { version: remoteTag })}
            </>
          )}
          {status === "error" && (
            <>
              <CircleAlert size={13} />
              {errorMsg}
            </>
          )}
        </span>

        {showOpenButton && (
          <button
            type="button"
            onClick={() => openReleases(status === "update" ? releaseUrl : undefined)}
            className="inline-flex items-center gap-1 text-primary hover:underline text-[0.75rem] font-medium"
            aria-label={t("updateOpenReleaseAria")}
          >
            {t("updateOpenRelease")}
            <ExternalLink size={12} />
          </button>
        )}

        <button
          type="button"
          onClick={handleCheck}
          disabled={checking}
          aria-label={t("updateCheckAria")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-glass-border text-primary hover:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-[0.75rem] font-medium"
        >
          {checking ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RefreshCw size={13} />
          )}
          {checking ? t("updateChecking") : t("updateCheck")}
        </button>
      </div>
    </div>
  );
}
