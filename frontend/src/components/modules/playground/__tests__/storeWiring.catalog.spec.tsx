import { screen, fireEvent } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * Store-wiring regression suite — the two catalog-driven controls.
 *
 * Same purpose as the sibling storeWiring specs (see compose spec header): pin
 * the `usePlaygroundStore` seam before D5 swaps it for an injected store.
 *
 * These two components also read the generated model catalog, which the
 * DashScope→Gemini migration is about to rewrite (four families deleted, two
 * added). So nothing here hard-codes a model id — expectations are derived from
 * `getModelsForMode()` at run time, leaving these tests sensitive to broken
 * store wiring and blind to catalog churn. Catalog contents have their own
 * coverage in src/__tests__/model-catalog.test.ts.
 */

vi.mock('lucide-react', () => {
    const cache = new Map<string, any>();
    return new Proxy({} as Record<string, any>, {
        get: (_target, prop) => {
            if (typeof prop !== 'string' || prop === 'then') return undefined;
            if (prop === '__esModule') return true;
            if (!cache.has(prop)) {
                const Icon = (props: any) => <span data-testid={`icon-${prop}`} {...props} />;
                Icon.displayName = prop;
                cache.set(prop, Icon);
            }
            return cache.get(prop);
        },
        has: () => true,
    });
});

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {},
    playgroundApi: {},
}));

import ModelSelector from '../ModelSelector';
import ParameterBar from '../ParameterBar';
import { getModelsForMode } from '../playgroundModels';
import { playgroundStore } from '../usePlaygroundStore';

const store = () => playgroundStore.getState();

beforeEach(() => {
    playgroundStore.setState({
        mode: 't2i',
        modelId: '',
        parameters: {},
        batchSize: 1,
    });
});

describe('ModelSelector ↔ store', () => {
    it('adopts a model for the store mode when the store holds none', () => {
        const expected = getModelsForMode('t2i')[0];
        renderWithIntl(<ModelSelector />);

        expect(store().modelId).toBe(expected.id);
    });

    it('re-picks a valid model when the store mode changes under it', () => {
        playgroundStore.setState({ mode: 't2v' });
        renderWithIntl(<ModelSelector />);

        const validForT2v = getModelsForMode('t2v').map((m) => m.id);
        expect(validForT2v).toContain(store().modelId);
    });

    it('writes the model the user picks back to the store', () => {
        const options = getModelsForMode('t2i');
        // Needs a second option to prove the click chose it rather than the
        // auto-adopt effect landing on the first one anyway.
        expect(options.length).toBeGreaterThan(1);
        renderWithIntl(<ModelSelector />);

        fireEvent.click(screen.getByRole('button', { name: new RegExp(options[0].displayName) }));
        fireEvent.click(screen.getByText(options[1].displayName));

        expect(store().modelId).toBe(options[1].id);
    });
});

describe('ParameterBar ↔ store', () => {
    it('marks the batch size held in the store', () => {
        playgroundStore.setState({ batchSize: 4 });
        renderWithIntl(<ParameterBar />);

        expect(screen.getByRole('button', { name: 'x4' }).className).toContain('bg-primary');
    });

    it('writes the chosen batch size back to the store', () => {
        renderWithIntl(<ParameterBar />);

        fireEvent.click(screen.getByRole('button', { name: 'x2' }));

        expect(store().batchSize).toBe(2);
    });

    it('does not clobber unrelated parameters when one control changes', () => {
        playgroundStore.setState({
            modelId: getModelsForMode('t2i')[0].id,
            parameters: { seed: 12345 },
        });
        renderWithIntl(<ParameterBar />);

        fireEvent.click(screen.getByRole('button', { name: 'x2' }));

        expect(store().parameters.seed).toBe(12345);
    });
});
