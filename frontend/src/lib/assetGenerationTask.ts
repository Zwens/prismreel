/**
 * The single-asset generation submit + poll path, shared by the Cast
 * workbench modal (one asset, user-tuned params) and the Cast batch button
 * (every pending asset, default params).
 *
 * Lives outside the modal because the batch queue needs to await a real
 * completion: its concurrency ceiling is meaningless if a task resolves as
 * soon as the submit request returns, while the asset is still rendering.
 */
import { api } from "@/lib/api";
import { toast } from "@/store/toastStore";

export type CastKind = "character" | "scene" | "prop";

export interface ImageVariant {
    id: string;
    url: string;
    is_favorited?: boolean;
}

/** Variants live in different slots depending on kind + legacy schema:
 *  · character → reference_sheet.image_variants (new) or full_body_asset.variants (legacy)
 *  · scene → image_asset.variants
 *  · prop → image_asset.variants
 *  Returns a normalized [{id, url, is_favorited?}] list. */
export function readVariants(entity: any, kind: CastKind): ImageVariant[] {
    if (!entity) return [];
    if (kind === "character") {
        const sheet = entity?.reference_sheet?.image_variants ?? [];
        if (sheet.length > 0) {
            return sheet.map((v: any) => ({ id: v.id, url: v.url, is_favorited: v.is_favorited }));
        }
        const legacy = entity?.full_body_asset?.variants ?? [];
        return legacy.map((v: any) => ({ id: v.id, url: v.url, is_favorited: v.is_favorited }));
    }
    const arr = entity?.image_asset?.variants ?? [];
    return arr.map((v: any) => ({ id: v.id, url: v.url, is_favorited: v.is_favorited }));
}

/** Characters generate a reference sheet; scenes and props generate a single
 *  image. The store keys its in-flight tasks by this value. */
export function generationTypeFor(kind: CastKind): string {
    return kind === "character" ? "reference_sheet" : "all";
}

// Module-level poll registry — survives modal close/reopen.
export const activePolls = new Map<string, ReturnType<typeof setInterval>>();

type Translate = (key: string, values?: any) => string;

interface PollStore {
    updateProject: (id: string, data: any) => void;
    removeGeneratingTask: (assetId: string, generationType: string) => void;
}

/** Poll a submitted task to its terminal state.
 *
 * Resolves when the asset finished, rejects when the backend reports a
 * failure or the poll itself breaks, so a caller can await one asset.
 */
export function startAssetPoll(
    entityId: string,
    taskId: string,
    projectId: string,
    kind: CastKind,
    generationType: string,
    t: Translate,
    getStore: () => PollStore,
    progressToastId?: string,
    intervalMs: number = 2500,
): Promise<void> {
    if (activePolls.has(entityId)) return Promise.resolve();

    return new Promise<void>((resolve, reject) => {
        const interval = setInterval(async () => {
            try {
                const status = await api.getTaskStatus(taskId);
                if (status?.status === "completed") {
                    clearInterval(interval);
                    activePolls.delete(entityId);
                    if (progressToastId) toast.dismiss(progressToastId);
                    const fresh = await api.getProject(projectId);
                    const { updateProject, removeGeneratingTask } = getStore();
                    updateProject(projectId, fresh);
                    removeGeneratingTask(entityId, generationType);
                    const entityPool = (kind === "character" ? fresh.characters : kind === "scene" ? fresh.scenes : fresh.props) || [];
                    const updatedEntity = entityPool.find((e: any) => e.id === entityId);
                    const count = updatedEntity ? readVariants(updatedEntity, kind).length : 0;
                    toast.success(t("toastVariantDone"), { body: t("toastVariantDoneBody", { count }) });
                    resolve();
                } else if (status?.status === "failed") {
                    clearInterval(interval);
                    activePolls.delete(entityId);
                    if (progressToastId) toast.dismiss(progressToastId);
                    const { removeGeneratingTask } = getStore();
                    removeGeneratingTask(entityId, generationType);
                    const detail = status?.error || t("toastGenErrUnknown");
                    toast.error(t("toastGenErr"), { body: detail });
                    reject(new Error(String(detail)));
                }
            } catch (err) {
                clearInterval(interval);
                activePolls.delete(entityId);
                if (progressToastId) toast.dismiss(progressToastId);
                const { removeGeneratingTask } = getStore();
                removeGeneratingTask(entityId, generationType);
                toast.error(t("toastPollErr"), { body: t("toastPollErrBody") });
                reject(err instanceof Error ? err : new Error(String(err)));
            }
        }, intervalMs);
        activePolls.set(entityId, interval);
    });
}

export interface SubmitAssetGenerationParams {
    projectId: string;
    entityId: string;
    kind: CastKind;
    prompt: string;
    stylePreset: string;
    stylePositive: string;
    negativePrompt: string;
    applyStyle: boolean;
    batchSize: number;
    model?: string;
    aspectRatio?: string;
    t: Translate;
    getStore: () => PollStore & {
        addGeneratingTask: (assetId: string, generationType: string, batchSize: number) => void;
    };
    progressToastId?: string;
    pollIntervalMs?: number;
}

/** Submit one asset generation and settle when it has actually finished.
 *
 * Marks the asset as generating up front so the card's overlay lights up,
 * and clears that state on every exit path — a stuck overlay reads as a
 * hung app.
 */
export async function submitAssetGeneration(
    params: SubmitAssetGenerationParams,
): Promise<void> {
    const {
        projectId, entityId, kind, prompt, stylePreset, stylePositive,
        negativePrompt, applyStyle, batchSize, model, aspectRatio,
        t, getStore, progressToastId, pollIntervalMs,
    } = params;

    const generationType = generationTypeFor(kind);
    const store = getStore();
    store.addGeneratingTask(entityId, generationType, batchSize);

    let resp: any;
    try {
        resp = await api.generateAsset(
            projectId,
            entityId,
            kind,
            stylePreset,
            applyStyle ? stylePositive : "",
            generationType,
            prompt,
            applyStyle,
            negativePrompt,
            batchSize,
            model,
            aspectRatio,
        );
    } catch (err: any) {
        if (progressToastId) toast.dismiss(progressToastId);
        getStore().removeGeneratingTask(entityId, generationType);
        const detail = err?.response?.data?.detail || err?.message || t("toastGenErrUnknown");
        toast.error(t("toastGenErr"), { body: String(detail) });
        throw err instanceof Error ? err : new Error(String(detail));
    }

    const taskId = resp?._task_id;
    if (taskId) {
        await startAssetPoll(
            entityId, taskId, projectId, kind, generationType,
            t, getStore, progressToastId, pollIntervalMs,
        );
        return;
    }

    // Synchronous render — the response is the updated project.
    if (progressToastId) toast.dismiss(progressToastId);
    const s = getStore();
    if (resp) s.updateProject(projectId, resp);
    s.removeGeneratingTask(entityId, generationType);
    toast.success(t("toastGenDone", { kind: t(`kind.${kind}`) }));
}
