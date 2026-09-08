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
    // 只在客户端执行，且只检查一次
    if (typeof window === 'undefined' || hasChecked || isPublicPage) return;

    checkEnvConfig();
    setHasChecked(true);
  }, [hasChecked, isPublicPage]);

  const checkEnvConfig = async () => {
    try {
      const config = await api.getEnvConfig();
      // 空值和空字符串都视为未配置。DashScope 是默认路由，但配置为
      // LLM_PROVIDER=openai（Gemini 等 OpenAI 兼容端点）并填了对应 key
      // 时同样视为已配置，不强制要求 DashScope。
      const dashscopeKey = config.DASHSCOPE_API_KEY?.trim();
      const openaiKey = config.OPENAI_API_KEY?.trim();
      const usingOpenAiProvider = config.LLM_PROVIDER === "openai";
      const hasRequired =
        (dashscopeKey && dashscopeKey.length > 0) ||
        (usingOpenAiProvider && openaiKey && openaiKey.length > 0);
      
      if (!hasRequired) {
        setEnvRequired(true);
        setIsEnvDialogOpen(true);
      }
    } catch (error) {
      console.error("Failed to check env config:", error);
      // 如果API调用失败，也显示配置对话框
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
