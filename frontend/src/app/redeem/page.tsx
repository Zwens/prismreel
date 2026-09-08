"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { redeemInvite } from "@/lib/api";

function RedeemInviteForm() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const code = searchParams.get("code") || "";
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await redeemInvite(code, email, password);
            router.push("/");
        } catch (err: any) {
            setError(err?.response?.data?.detail || "邀請碼無效或已使用");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <form onSubmit={handleSubmit} className="glass-panel atelier-card p-8 w-full max-w-sm space-y-4">
                <h1 className="text-2xl font-display">建立帳號</h1>
                <div>
                    <label className="block text-sm mb-1">Email</label>
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="w-full px-3 py-2 rounded border" />
                </div>
                <div>
                    <label className="block text-sm mb-1">設定密碼</label>
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="w-full px-3 py-2 rounded border" />
                </div>
                {error && <p className="text-sm text-red-500">{error}</p>}
                <button type="submit" disabled={loading} className="w-full py-2 rounded bg-black text-white">
                    {loading ? "建立中..." : "建立帳號"}
                </button>
            </form>
        </div>
    );
}

export default function RedeemInvitePage() {
    return (
        <Suspense fallback={null}>
            <RedeemInviteForm />
        </Suspense>
    );
}
