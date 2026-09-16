import rawCatalog from '@/generated/modelCatalog.json';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    DEFAULT_MODEL_SETTINGS,
    GLOBAL_I2I_MODELS,
    GLOBAL_I2V_MODELS,
    GLOBAL_IMAGE_MODELS,
    GLOBAL_T2I_MODELS,
    R2V_ROUTE_MODEL_ID,
    R2V_SELECTION_MODEL_ID,
    getCanonicalDefaults,
    getCanonicalModeEntry,
    getCanonicalModeId,
    getLegacyModelId,
    getMaxReferenceImages,
    getReferenceSlotCapacity,
    getModelLineEntry,
    getModeGateway,
    resolveModelSettings,
} from '@/lib/modelCatalog';

type MockCatalog = Omit<typeof rawCatalog, 'model_lines' | 'modes' | 'compat'> & {
    model_lines?: Record<string, { id: string; family: string }>;
    modes?: Record<string, { id: string; model_line_id: string; mode: string }>;
    compat?: {
        legacy_model_ids?: Record<string, string>;
    };
};

afterEach(() => {
    vi.doUnmock('@/generated/modelCatalog.json');
    vi.resetModules();
});

describe('model catalog selectors', () => {
    it('derives visible model selectors from catalog defaults', () => {
        // Defaults follow the catalog upgrade to wan2.7 (Phase 2, 2026-Q1).
        // The unified `image_model` surface replaces the per-mode t2i/i2i
        // settings at the consumer layer.
        expect(DEFAULT_MODEL_SETTINGS).toMatchObject({
            t2i_model: 'gemini-3.1-flash-image',
            i2i_model: 'gemini-3.1-flash-image',
            i2v_model: 'seedance-2.5-i2v',
            image_model: 'gemini-3.1-flash-image',
        });

        // The 't2i' and 'i2i' selection_group surfaces moved to 'image'
        // in Phase 2. The resolver now falls through to visible image-group
        // models so user picks (e.g. Wan 2.7 Image Pro) persist through
        // resolveModelId() instead of silently reverting to the default.
        expect(GLOBAL_T2I_MODELS.map((model) => model.id)).toEqual(GLOBAL_IMAGE_MODELS.map((m) => m.id));
        expect(GLOBAL_I2I_MODELS.map((model) => model.id)).toEqual(GLOBAL_IMAGE_MODELS.map((m) => m.id));

        // Ordered DESC by ui.order; ties broken by display_name asc.
        expect(GLOBAL_I2V_MODELS.map((model) => model.id)).toEqual([
            // DESC by ui.order；同序按 display_name 升序。DashScope 下线后
            // wan / happyhorse / pixverse 全部消失，只剩这三家。
            'kling-v3-i2v',
            'seedance-2.5-i2v',
            'seedance-2.0-fast-i2v',
            'seedance-2.0-i2v',
            'seedance-2.0-mini-i2v',
            'viduq3-pro-i2v',
            'viduq3-turbo-i2v',
        ]);
    });

    it('keeps hidden and planned catalog entries out of visible selectors', () => {
        expect(GLOBAL_I2V_MODELS.some((model) => model.id === 'seedance-2.5-r2v')).toBe(false);
        expect(GLOBAL_I2V_MODELS.some((model) => model.id === 'pixverse-v4-i2v')).toBe(false);
    });
});

describe('model catalog fallbacks', () => {
    it('falls back unknown and legacy-surface ids to catalog defaults', () => {
        expect(
            resolveModelSettings(
                {
                    t2i_model: 'missing-model',
                    i2i_model: 'seedance-2.5-r2v',
                    i2v_model: 'missing-video-model',
                },
                'global_settings'
            )
        ).toMatchObject({
            t2i_model: 'gemini-3.1-flash-image',
            i2i_model: 'gemini-3.1-flash-image',
            i2v_model: 'seedance-2.5-i2v',
        });
    });

    it('normalizes canonical mode ids back to legacy compatibility ids when compat metadata exists', async () => {
        const catalogWithCompat = structuredClone(rawCatalog) as MockCatalog;
        catalogWithCompat.model_lines = {
            'gemini/gemini-image': {
                id: 'gemini/gemini-image',
                family: 'seedance',
            },
            'seedance/seedance-2.5-video': {
                id: 'seedance/seedance-2.5-video',
                family: 'seedance',
            },
        };
        catalogWithCompat.modes = {
            'gemini/gemini-image#i2i': {
                id: 'gemini/gemini-image#i2i',
                model_line_id: 'gemini/gemini-image',
                mode: 'i2i',
            },
            'seedance/seedance-2.5-video#i2v': {
                id: 'seedance/seedance-2.5-video#i2v',
                model_line_id: 'seedance/seedance-2.5-video',
                mode: 'i2v',
            },
            'seedance/seedance-2.5-video#r2v': {
                id: 'seedance/seedance-2.5-video#r2v',
                model_line_id: 'seedance/seedance-2.5-video',
                mode: 'r2v',
            },
        };
        catalogWithCompat.compat = {
            legacy_model_ids: {
                'gemini-3.1-flash-image': 'gemini/gemini-image#i2i',
                'seedance-2.5-i2v': 'seedance/seedance-2.5-video#i2v',
                'seedance-2.5-r2v': 'seedance/seedance-2.5-video#r2v',
            },
        };

        vi.doMock('@/generated/modelCatalog.json', () => ({
            default: catalogWithCompat,
        }));

        const {
            GLOBAL_I2V_MODELS: compatI2vModels,
            R2V_ROUTE_MODEL_ID: compatR2vRouteModelId,
            R2V_SELECTION_MODEL_ID: compatR2vSelectionModelId,
            resolveModelSettings: resolveCompatModelSettings,
        } = await import('@/lib/modelCatalog');

        // After 524f3a1 deprecated the wan2.6 series, 'seedance-2.5-i2v' is hidden
        // (visible_in: []), so the canonical → legacy normalization is filtered
        // out by the visibility check and the resolver falls back to the current
        // i2v default (seedance-2.5-i2v). The raw normalization contract is
        // covered directly by the Phase 2 canonical helpers below.
        expect(
            resolveCompatModelSettings(
                {
                    i2v_model: 'seedance/seedance-2.5-video#i2v',
                },
                'global_settings'
            ).i2v_model
        ).toBe('seedance-2.5-i2v');

        // An r2v canonical id normalizes to the matching legacy id
        // (seedance-2.5-r2v), which is hidden in the i2v surface — so the
        // resolver falls back to the current i2v default (seedance-2.5-i2v
        // since the 2026-05-26 catalog meta switch). Previously this
        // assertion expected the resolver to remap r2v into the parent
        // i2v legacy id; that behavior was dropped when r2v ids gained
        // explicit modality suffixes.
        expect(
            resolveCompatModelSettings(
                {
                    i2v_model: 'seedance/seedance-2.5-video#r2v',
                },
                'global_settings'
            ).i2v_model
        ).toBe('seedance-2.5-i2v');

        // 兼容视图里不应出现 canonical 形式的 id —— 那是内部表示，
        // 泄漏到选择器会让用户选到一个后端不认的字符串。
        expect(compatI2vModels.some((model) => model.id.includes('#'))).toBe(false);
        // R2V selection/route ids follow the catalog meta default
        // (defaults.model_settings.r2v_model = seedance-2.5-r2v) via
        // getFallbackVisibleModelId, not raw ui.order. Several R2V models
        // share order=80, so anchoring to the explicit meta default keeps the
        // default route deterministic. Selection and route are unified
        // (R2V_ROUTE_MODEL_ID = R2V_SELECTION_MODEL_ID).
        expect(compatR2vSelectionModelId).toBe('seedance-2.5-r2v');
        expect(compatR2vRouteModelId).toBe('seedance-2.5-r2v');
    });
});

describe('model catalog runtime helpers', () => {
    it('derives the current R2V selection and route ids from catalog data', () => {
        // Selection and route both resolve to the catalog meta default R2V
        // model (defaults.model_settings.r2v_model = seedance-2.5-r2v) via
        // getFallbackVisibleModelId — deterministic regardless of the order=80
        // tie among visible R2V models (happyhorse/kling/seedance/wan2.7).
        expect(R2V_SELECTION_MODEL_ID).toBe('seedance-2.5-r2v');
        expect(R2V_ROUTE_MODEL_ID).toBe('seedance-2.5-r2v');
    });

    it('reads per-model reference image limits from catalog metadata', () => {
        // getMaxReferenceImages routes the input through resolveModelId
        // for the 'i2i' surface — when the literal id isn't visible in
        // that surface (post-Phase 2 the wan2.6 ids moved to the
        // 'image' selection_group), the resolver falls back to the
        // current default (wan2.7-image, which advertises 9 refs).
        // The behavior is correct given how callers (PropertiesPanel)
        // use the project's i2i_model setting.
        // Gemini 单次最多 14 张参考图（10 物体 + 4 角色一致性），强于原 Wan 通道。
        expect(getMaxReferenceImages('gemini-3.1-flash-image')).toBe(14);
        expect(getMaxReferenceImages('gemini-3-pro-image')).toBe(14);
    });

    it('reads the reference slot budget of an already-resolved video model', () => {
        // getMaxReferenceImages forces its input through the 'i2i' surface,
        // so it cannot answer for a video model. R2V slot filling needs the
        // literal id's own budget — these differ per vendor and a wrong
        // ceiling means silently dropped references.
        expect(getReferenceSlotCapacity('seedance-2.5-r2v')).toBe(50);
        expect(getReferenceSlotCapacity('viduq3-drama-r2v')).toBe(7);
    });

    it('falls back to a single slot for a model with no declared budget', () => {
        expect(getReferenceSlotCapacity('nonexistent-model')).toBe(1);
    });
});

describe('model catalog phase 2 canonical helpers', () => {
    it('resolves legacy flat id to canonical mode id', () => {
        expect(getCanonicalModeId('seedance-2.5-i2v')).toBe('seedance/seedance-2.5-video#i2v');
        expect(getCanonicalModeId('seedance-2.5-r2v')).toBe('seedance/seedance-2.5-video#r2v');
        expect(getCanonicalModeId('nonexistent')).toBeUndefined();
    });

    it('resolves canonical mode id back to legacy flat id', () => {
        expect(getLegacyModelId('seedance/seedance-2.5-video#i2v')).toBe('seedance-2.5-i2v');
        expect(getLegacyModelId('seedance/seedance-2.5-video#r2v')).toBe('seedance-2.5-r2v');
        expect(getLegacyModelId('nonexistent')).toBeUndefined();
    });

    it('reads canonical mode entry with full metadata', () => {
        const entry = getCanonicalModeEntry('seedance/seedance-2.5-video#i2v');
        expect(entry).not.toBeNull();
        expect(entry?.model_line_id).toBe('seedance/seedance-2.5-video');
        expect(entry?.legacy_model_id).toBe('seedance-2.5-i2v');
        expect(entry?.mode).toBe('i2v');
        expect(entry?.family).toBe('seedance');

        expect(getCanonicalModeEntry('nonexistent')).toBeNull();
    });

    it('reads model line entry', () => {
        const line = getModelLineEntry('seedance/seedance-2.5-video');
        expect(line).not.toBeNull();
        expect(line?.family).toBe('seedance');
        expect(line?.modes).toContain('seedance/seedance-2.5-video#i2v');
        expect(line?.modes).toContain('seedance/seedance-2.5-video#r2v');
        expect(line?.legacy_model_ids).toContain('seedance-2.5-i2v');

        expect(getModelLineEntry('nonexistent')).toBeNull();
    });

    it('reads gateway metadata from canonical mode runtime', () => {
        expect(getModeGateway('seedance/seedance-2.5-video#r2v', 'byteplus')).toBe('byteplus');
        expect(getModeGateway('seedance/seedance-2.5-video#r2v', 'vendor')).toBeUndefined();
        expect(getModeGateway('nonexistent', 'byteplus')).toBeUndefined();
    });

    it('reads canonical default model settings', () => {
        const defaults = getCanonicalDefaults();
        expect(defaults.t2i_model).toContain('#');
        expect(defaults.i2i_model).toContain('#');
        expect(defaults.i2v_model).toContain('#');
    });

    it('does not leak canonical ids into visible flat model selectors', () => {
        for (const model of GLOBAL_I2V_MODELS) {
            expect(model.id).not.toContain('#');
        }
        for (const model of GLOBAL_T2I_MODELS) {
            expect(model.id).not.toContain('#');
        }
        for (const model of GLOBAL_I2I_MODELS) {
            expect(model.id).not.toContain('#');
        }
    });
});
