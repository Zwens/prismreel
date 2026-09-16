/**
 * Models whose provider has no credentials configured must be identifiable.
 *
 * Seedance (all versions) needs ARK_API_KEY, which is unset in this install
 * — yet Seedance models were offered in the model pickers as ordinary choices.
 * Picking one produced a generation that failed at the provider with an auth
 * error, long after the user had committed to the shot.
 *
 * The catalog already carries family -> required env keys
 * (`families[x].credential_sources`), and GET /config/env reports which keys
 * hold a value, so this is decidable in the UI before anything is submitted.
 */
import { describe, it, expect } from 'vitest';
import {
    modelRequiresCredentials,
    isModelCredentialReady,
} from '@/lib/modelCatalog';

describe('modelRequiresCredentials', () => {
    it('列出 seedance 2.0 需要的环境变量', () => {
        expect(modelRequiresCredentials('seedance-2.0-r2v')).toEqual(['ARK_API_KEY']);
    });

    it('fast 变体与标准变体要求一致', () => {
        expect(modelRequiresCredentials('seedance-2.0-fast-r2v')).toEqual(['ARK_API_KEY']);
    });

    it('同家族不同 backend 的凭据互不串用', () => {
        // Seedance family all run on BytePlus Ark.
        expect(modelRequiresCredentials('seedance-2.5-r2v')).toEqual(['ARK_API_KEY']);
        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: 'ark-live-x' })).toBe(true);
        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: '' })).toBe(false);
    });

    it('Gemini 图像模型要求 GEMINI_API_KEY', () => {
        expect(modelRequiresCredentials('gemini-3.1-flash-image')).toContain('GEMINI_API_KEY');
    });

    it('未知模型返回空数组，不误报', () => {
        expect(modelRequiresCredentials('nonexistent-model')).toEqual([]);
    });
});

describe('isModelCredentialReady', () => {
    it('所需变量有值时判定就绪', () => {
        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: 'sk-live-x' })).toBe(true);
    });

    it('所需变量为空串时判定未就绪 —— /config/env 用空串表示未配置', () => {
        expect(isModelCredentialReady('seedance-2.0-r2v', { ARK_API_KEY: '' })).toBe(false);
    });

    it('所需变量缺失时判定未就绪', () => {
        expect(isModelCredentialReady('seedance-2.0-r2v', {})).toBe(false);
    });

    it('多选一：任一凭据可用即就绪', () => {
        // kling accepts either DashScope or its own access key.
        const required = modelRequiresCredentials('kling-v3-i2v');
        expect(required.length).toBeGreaterThan(1);
        expect(isModelCredentialReady('kling-v3-i2v', { [required[0]]: 'x' })).toBe(true);
    });

    it('不要求凭据的模型永远就绪，不因配置为空被误禁', () => {
        expect(isModelCredentialReady('nonexistent-model', {})).toBe(true);
    });
});
