"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
    adminListUsers,
    adminCreateInvite,
    adminResetPassword,
    adminDeactivateUser,
    getCurrentUser,
    getAllUsersUsage,
    type AdminUser,
    type UsageSummary,
} from "@/lib/api";

export default function AdminUsersPage() {
    const router = useRouter();
    const t = useTranslations("usage");
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [inviteLink, setInviteLink] = useState("");
    const [loading, setLoading] = useState(true);
    const [authorized, setAuthorized] = useState(false);
    const [usageData, setUsageData] = useState<{ user_id: string; summary: UsageSummary }[]>([]);

    useEffect(() => {
        getCurrentUser()
            .then((me) => {
                if (me.role !== "admin") {
                    router.push("/");
                    return;
                }
                setAuthorized(true);
                getAllUsersUsage().then(setUsageData).catch(() => {});
                return adminListUsers();
            })
            .then((data) => {
                if (data) setUsers(data);
            })
            .finally(() => setLoading(false));
    }, [router]);

    async function handleCreateInvite() {
        const { invite_code } = await adminCreateInvite();
        setInviteLink(`${window.location.origin}/redeem?code=${invite_code}`);
    }

    async function handleResetPassword(userId: string) {
        const newPassword = window.prompt("輸入新密碼");
        if (!newPassword) return;
        await adminResetPassword(userId, newPassword);
        window.alert("密碼已重設");
    }

    async function handleDeactivate(userId: string) {
        if (!window.confirm("確定停用此帳號？")) return;
        await adminDeactivateUser(userId);
        const data = await adminListUsers();
        setUsers(data);
    }

    if (loading || !authorized) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <p className="text-text-secondary">載入中...</p>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background p-8">
            <div className="max-w-3xl mx-auto space-y-6">
                <h1 className="text-2xl font-display">使用者管理</h1>

                <div className="glass-panel atelier-card p-6 space-y-3">
                    <button
                        onClick={handleCreateInvite}
                        className="px-4 py-2 rounded bg-black text-white"
                    >
                        建立邀請連結
                    </button>
                    {inviteLink && (
                        <div className="glass-panel p-3 text-sm break-all">{inviteLink}</div>
                    )}
                </div>

                <div className="glass-panel atelier-card p-6">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left border-b border-glass-border">
                                <th className="pb-2">Email</th>
                                <th className="pb-2">角色</th>
                                <th className="pb-2">狀態</th>
                                <th className="pb-2">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map((u) => (
                                <tr key={u.id} className="border-b border-glass-border last:border-0">
                                    <td className="py-2">{u.email}</td>
                                    <td className="py-2">{u.role}</td>
                                    <td className="py-2">{u.is_active ? "啟用" : "停用"}</td>
                                    <td className="py-2 space-x-3">
                                        <button
                                            onClick={() => handleResetPassword(u.id)}
                                            className="text-primary hover:underline"
                                        >
                                            重設密碼
                                        </button>
                                        {u.is_active && (
                                            <button
                                                onClick={() => handleDeactivate(u.id)}
                                                className="text-red-500 hover:underline"
                                            >
                                                停用
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="glass-panel atelier-card p-6">
                    <h2 className="text-lg font-display mb-3">{t("adminUsageTitle")}</h2>
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left border-b border-glass-border">
                                <th className="pb-2">User ID</th>
                                <th className="pb-2">{t("columnCost")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {usageData.map((u) => {
                                let totalCost = 0;
                                for (const providers of Object.values(u.summary)) {
                                    for (const models of Object.values(providers)) {
                                        for (const bucket of Object.values(models)) {
                                            if (bucket.cost_usd != null) totalCost += bucket.cost_usd;
                                        }
                                    }
                                }
                                return (
                                    <tr key={u.user_id} className="border-b border-glass-border last:border-0">
                                        <td className="py-2 font-mono text-xs">{u.user_id || "unknown"}</td>
                                        <td className="py-2">${totalCost.toFixed(4)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
