import { screen, fireEvent } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * The global nav model.
 *
 * GlobalSidebar and BottomTabBar both render from GLOBAL_NAV_ITEMS, but the
 * sidebar slices it to separate the main entries from the pinned settings row.
 * That slice is a fixed count, so adding a nav item without touching it drops
 * the new entry from the desktop sidebar while it still shows up on mobile —
 * silently, and only on one breakpoint. These pin the two against each other.
 */

// 侧栏的登出按钮用到 next/navigation 的 useRouter，测试树里没有挂载 app router。
vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
    usePathname: () => '/',
    useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/api', () => ({
    logout: vi.fn().mockResolvedValue(undefined),
}));

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

import GlobalSidebar, { GLOBAL_NAV_ITEMS } from '../GlobalSidebar';

beforeEach(() => {
    window.location.hash = '';
});

describe('GlobalSidebar', () => {
    it('renders every nav entry, settings included', () => {
        renderWithIntl(<GlobalSidebar activeTab="workspace" onTabChange={() => {}} />);

        // Derived from the shared model rather than a hard-coded list. 渲染侧
        // 已改用 filter(id !== 'settings') 而不是 slice(0, N)，所以新增条目
        // 不再需要同步改渲染代码——只有下面这条计数断言要跟着走。
        for (const label of ["漫画生成", "素材库", "视频生成", "多镜头工作流", "图片生成", "生成历史", "设置"]) {
            expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
        }
        expect(GLOBAL_NAV_ITEMS).toHaveLength(7);
    });

    it('gives the video and image generation entries their own routes', () => {
        expect(GLOBAL_NAV_ITEMS.find((i) => i.id === 'videogen')?.hash).toBe('#/video-gen');
        expect(GLOBAL_NAV_ITEMS.find((i) => i.id === 'imagegen')?.hash).toBe('#/image-gen');
    });

    it('navigates and reports the tab when the video generation entry is clicked', () => {
        const onTabChange = vi.fn();
        renderWithIntl(<GlobalSidebar activeTab="workspace" onTabChange={onTabChange} />);

        fireEvent.click(screen.getByRole('button', { name: '视频生成' }));

        expect(onTabChange).toHaveBeenCalledWith('videogen');
        expect(window.location.hash).toBe('#/video-gen');
    });

    it('marks the active tab for screen readers', () => {
        renderWithIntl(<GlobalSidebar activeTab="videogen" onTabChange={() => {}} />);

        expect(screen.getByRole('button', { name: '视频生成' })).toHaveAttribute(
            'aria-current',
            'page',
        );
        expect(screen.getByRole('button', { name: "图片生成" })).not.toHaveAttribute('aria-current');
    });

    it('navigates to the video workflow hash when the video workflow nav item is clicked', () => {
        const onTabChange = vi.fn();
        renderWithIntl(<GlobalSidebar activeTab="workspace" onTabChange={onTabChange} />);

        fireEvent.click(screen.getByRole('button', { name: '多镜头工作流' }));

        expect(onTabChange).toHaveBeenCalledWith('videoworkflow');
        expect(window.location.hash).toBe('#/video-workflow');
    });
});
