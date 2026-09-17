"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import EnvConfigDialog from "@/components/project/EnvConfigDialog";
import { api } from "@/lib/api";

// Public auth pages render before login, so the env-config API call would
// always 401 under the login gate and misleadingly show "env not configured".
const _PUBLIC_PATH_PREFIXES = ["/login", "/redeem"];

export default function EnvConfigChecker() {
  const pathname = usePathname();
  const [isEnvDialogOpen, setIsEnvDialogOpen] = useState(false);
  const [envRequired, setEnvRequired] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);

  const isPublicPage = _PUBLIC_PATH_PREFIXES.some((p) => pathname?.startsWith(p));

  useEffect(() => {
    // 只在客戶端執行，且只檢查一次
    if (typeof window === 'undefined' || hasChecked || isPublicPage) return;

    checkEnvConfig();
    setHasChecked(true);
  }, [hasChecked, isPublicPage]);

  const checkEnvConfig = async () => {
    try {
      const config = await api.getEnvConfig();
      // 空值和空字符串都視為未配置。Gemini 是默認路由，但配置為
      // LLM_PROVIDER=openai（第三方 OpenAI 兼容端點）並填了對應 key
      // 時同樣視為已配置，不強制要求 Gemini。
      const asText = (v: unknown) => (typeof v === "string" ? v.trim() : "");
      const geminiKey = asText(config.GEMINI_API_KEY);
      const openaiKey = asText(config.OPENAI_API_KEY);
      const usingOpenAiProvider = config.LLM_PROVIDER === "openai";
      const hasRequired =
        (geminiKey && geminiKey.length > 0) ||
        (usingOpenAiProvider && openaiKey && openaiKey.length > 0);
      
      if (!hasRequired) {
        setEnvRequired(true);
        setIsEnvDialogOpen(true);
      }
    } catch (error) {
      console.error("Failed to check env config:", error);
      // 如果API調用失敗，也顯示配置對話框
      setEnvRequired(true);
      setIsEnvDialogOpen(true);
    }
  };

  if (isPublicPage) return null;

  return (
    <EnvConfigDialog
      isOpen={isEnvDialogOpen}
      onClose={() => {
        setIsEnvDialogOpen(false);
        setEnvRequired(false);
      }}
      isRequired={envRequired}
    />
  );
}
