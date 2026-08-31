/**
 * Batch asset generation helpers for Cast Step 3「一键生成所有素材」.
 *
 * The per-asset submit path (prompt template, style, poll) is unchanged —
 * this module only decides *which* assets go into the batch and *how many
 * at a time*, so both are testable without touching the API or the store.
 */

/** Variants per asset in a batch run.
 *
 * The workbench modal defaults to 2. A batch covers every pending asset at
 * once, so keeping 2 would quietly double the spend on a run the user
 * triggered with a single click. One variant each; refine individually
 * afterwards in the workbench.
 */
export const BATCH_VARIANT_COUNT = 1;

/** How many generations may be in flight at once.
 *
 * Each submit is its own request and the backend runs them on separate
 * threads, so firing all of them together is a straight shot at the image
 * provider's rate limit.
 */
export const BATCH_CONCURRENCY = 2;

interface PendingCandidate {
    status: "ready" | "pending" | "new";
}

/** Assets still waiting for a reference image. Already-generated assets are
 *  skipped so a batch run never overwrites a result the user kept. */
export function pickPendingAssets<T extends PendingCandidate>(items: T[]): T[] {
    return items.filter((item) => item.status === "pending");
}

/** How many shots may be generating video at once.
 *
 * The backend puts no ceiling on this — each submit spawns its own background
 * task — so looping over a 13-shot storyboard would open 13 concurrent
 * provider calls. Video is the slow, expensive step; two at a time keeps the
 * queue moving without tripping rate limits.
 */
export const BATCH_VIDEO_CONCURRENCY = 2;

export type BatchVideoSkipReason =
    | "already-generated"
    | "in-flight"
    | "missing-refs"
    | "missing-first-frame";

interface PlannableShot {
    tabMode: "t2i_i2v" | "direct_r2v";
    videoUrl?: string;
    videoTaskId?: string;
    videoStatus?: "pending" | "processing" | "completed" | "failed";
}

export interface BatchVideoPlan<T> {
    ready: T[];
    skipped: Array<{ shot: T; reason: BatchVideoSkipReason }>;
}

export interface BatchVideoProbes<T> {
    /** R2V shots need at least one resolvable reference image. */
    hasReferences: (shot: T) => boolean;
    /** I2V shots need a first frame instead. */
    hasFirstFrame: (shot: T) => boolean;
}

/** Decide which shots a batch video run will touch, and why the rest are out.
 *
 * Computed before anything is submitted so the confirm dialog can name the
 * excluded shots. A shot whose last attempt failed is deliberately eligible
 * again — retrying the failures is most of the point of a batch run.
 */
export function planBatchVideoRun<T extends PlannableShot>(
    shots: readonly T[],
    probes: BatchVideoProbes<T>,
): BatchVideoPlan<T> {
    const ready: T[] = [];
    const skipped: Array<{ shot: T; reason: BatchVideoSkipReason }> = [];

    for (const shot of shots) {
        if (shot.videoUrl || shot.videoStatus === "completed") {
            skipped.push({ shot, reason: "already-generated" });
            continue;
        }
        if (shot.videoTaskId && (shot.videoStatus === "pending" || shot.videoStatus === "processing")) {
            skipped.push({ shot, reason: "in-flight" });
            continue;
        }
        if (shot.tabMode === "direct_r2v") {
            if (!probes.hasReferences(shot)) {
                skipped.push({ shot, reason: "missing-refs" });
                continue;
            }
        } else if (!probes.hasFirstFrame(shot)) {
            skipped.push({ shot, reason: "missing-first-frame" });
            continue;
        }
        ready.push(shot);
    }

    return { ready, skipped };
}

export interface BatchRunResult {
    succeeded: number;
    failed: number;
}

/** Run task factories with a ceiling on in-flight work.
 *
 * A rejected task counts as failed and the queue keeps going — one asset
 * whose prompt the backend rejects must not strand the rest of the batch.
 */
export async function runWithConcurrencyLimit(
    factories: Array<() => Promise<unknown>>,
    limit: number,
): Promise<BatchRunResult> {
    const result: BatchRunResult = { succeeded: 0, failed: 0 };
    let cursor = 0;

    const worker = async (): Promise<void> => {
        while (cursor < factories.length) {
            const index = cursor;
            cursor += 1;
            try {
                await factories[index]();
                result.succeeded += 1;
            } catch {
                result.failed += 1;
            }
        }
    };

    const workers = Array.from(
        { length: Math.max(1, Math.min(limit, factories.length)) },
        () => worker(),
    );
    await Promise.all(workers);

    return result;
}
