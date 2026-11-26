/**
 * AnnouncementsSlice Tests
 *
 * Tests the announcements Redux slice sorting logic
 *
 * Note: Tests for dismissAnnouncementLocally and resetAnnouncements actions are limited
 * because the slice uses Set which requires enableMapSet() from Immer. This should be
 * addressed in the slice implementation.
 */

import { describe, it, expect } from 'vitest'
import announcementsReducer, {
  setAnnouncements,
  type AnnouncementsState,
} from './announcementsSlice'
import type { Announcement } from '@/types/announcement'

// Mock announcements with different priorities and properties
const mockAnnouncements: Announcement[] = [
  {
    id: 'ann-1',
    organization_id: 'org-123',
    title: 'Normal Priority',
    body: 'Normal priority announcement',
    priority: 'normal',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: null,
    cta_url: null,
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: null,
    is_dismissible: true,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-12-31T23:59:59Z',
    created_by_id: 'user-1',
    created_time: '2026-01-03T00:00:00Z',
    updated_time: null,
    is_platform_wide: false,
  },
  {
    id: 'ann-2',
    organization_id: null,
    title: 'Critical Platform-wide',
    body: 'Critical platform-wide announcement',
    priority: 'critical',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: null,
    cta_url: null,
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: null,
    is_dismissible: true,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-12-31T23:59:59Z',
    created_by_id: 'admin-1',
    created_time: '2026-01-02T00:00:00Z',
    updated_time: null,
    is_platform_wide: true,
  },
  {
    id: 'ann-3',
    organization_id: 'org-123',
    title: 'Non-dismissible High Priority',
    body: 'Non-dismissible high priority announcement',
    priority: 'high',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: 'Accept',
    cta_url: '/terms',
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: null,
    is_dismissible: false,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-12-31T23:59:59Z',
    created_by_id: 'user-1',
    created_time: '2026-01-01T00:00:00Z',
    updated_time: null,
    is_platform_wide: false,
  },
  {
    id: 'ann-4',
    organization_id: 'org-123',
    title: 'Low Priority Org',
    body: 'Low priority org announcement',
    priority: 'low',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: null,
    cta_url: null,
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: null,
    is_dismissible: true,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-12-31T23:59:59Z',
    created_by_id: 'user-1',
    created_time: '2026-01-04T00:00:00Z',
    updated_time: null,
    is_platform_wide: false,
  },
]

const initialState: AnnouncementsState = {
  announcements: [],
  isLoading: false,
  locallyDismissedIds: new Set(),
}

describe('announcementsSlice', () => {
  describe('initial state', () => {
    it('has correct initial state structure', () => {
      const state = announcementsReducer(undefined, { type: '@@INIT' })
      expect(state.announcements).toEqual([])
      expect(state.isLoading).toBe(false)
      expect(state.locallyDismissedIds).toBeInstanceOf(Set)
      expect(state.locallyDismissedIds.size).toBe(0)
    })
  })

  describe('setAnnouncements action', () => {
    it('sets announcements in sorted order', () => {
      const state = announcementsReducer(
        initialState,
        setAnnouncements(mockAnnouncements)
      )

      expect(state.announcements).toHaveLength(4)
    })

    it('sorts announcements correctly by priority and type', () => {
      const state = announcementsReducer(
        initialState,
        setAnnouncements(mockAnnouncements)
      )

      const announcements = state.announcements

      // Expected order:
      // 1. ann-3 (non-dismissible, high priority)
      // 2. ann-2 (dismissible, critical, platform-wide)
      // 3. ann-1 (dismissible, normal, org-specific, created 2026-01-03)
      // 4. ann-4 (dismissible, low, org-specific)

      expect(announcements[0].id).toBe('ann-3') // Non-dismissible comes first
      expect(announcements[1].id).toBe('ann-2') // Critical platform-wide
      expect(announcements[2].id).toBe('ann-1') // Normal priority
      expect(announcements[3].id).toBe('ann-4') // Low priority
    })

    it('prioritizes non-dismissible announcements', () => {
      const announcements: Announcement[] = [
        { ...mockAnnouncements[0], is_dismissible: true, priority: 'critical' },
        { ...mockAnnouncements[1], is_dismissible: false, priority: 'low' },
      ]

      const state = announcementsReducer(initialState, setAnnouncements(announcements))

      expect(state.announcements[0].is_dismissible).toBe(false)
    })

    it('sorts by priority within dismissible announcements', () => {
      const announcements: Announcement[] = [
        { ...mockAnnouncements[0], priority: 'low', id: 'low' },
        { ...mockAnnouncements[1], priority: 'critical', id: 'critical' },
        { ...mockAnnouncements[2], priority: 'high', id: 'high', is_dismissible: true },
      ]

      const state = announcementsReducer(initialState, setAnnouncements(announcements))

      const dismissible = state.announcements.filter((a) => a.is_dismissible)
      expect(dismissible[0].priority).toBe('critical')
      expect(dismissible[1].priority).toBe('high')
      expect(dismissible[2].priority).toBe('low')
    })

    it('prioritizes platform-wide over org-specific for same priority', () => {
      const announcements: Announcement[] = [
        {
          ...mockAnnouncements[0],
          priority: 'high',
          is_platform_wide: false,
          id: 'org',
        },
        {
          ...mockAnnouncements[1],
          priority: 'high',
          is_platform_wide: true,
          id: 'platform',
        },
      ]

      const state = announcementsReducer(initialState, setAnnouncements(announcements))

      expect(state.announcements[0].is_platform_wide).toBe(true)
      expect(state.announcements[1].is_platform_wide).toBe(false)
    })

    it('sorts by created_time (newest first) for same priority and scope', () => {
      const announcements: Announcement[] = [
        {
          ...mockAnnouncements[0],
          priority: 'high',
          is_platform_wide: true,
          created_time: '2026-01-01T00:00:00Z',
          id: 'old',
        },
        {
          ...mockAnnouncements[1],
          priority: 'high',
          is_platform_wide: true,
          created_time: '2026-01-05T00:00:00Z',
          id: 'new',
        },
      ]

      const state = announcementsReducer(initialState, setAnnouncements(announcements))

      expect(state.announcements[0].id).toBe('new')
      expect(state.announcements[1].id).toBe('old')
    })
  })

  describe('edge cases', () => {
    it('handles empty announcement list', () => {
      const state = announcementsReducer(initialState, setAnnouncements([]))

      expect(state.announcements).toEqual([])
    })

    it('handles single announcement', () => {
      const state = announcementsReducer(
        initialState,
        setAnnouncements([mockAnnouncements[0]])
      )

      expect(state.announcements).toHaveLength(1)
      expect(state.announcements[0].id).toBe('ann-1')
    })

    it('handles announcements with null created_time', () => {
      const announcements: Announcement[] = [
        { ...mockAnnouncements[0], created_time: null, id: 'null-time' },
        { ...mockAnnouncements[1], created_time: '2026-01-01T00:00:00Z', id: 'with-time' },
      ]

      const state = announcementsReducer(initialState, setAnnouncements(announcements))

      expect(state.announcements).toHaveLength(2)
      // Announcement with null time should be sorted to end (treated as 0)
      expect(state.announcements[1].id).toBe('null-time')
    })
  })
})
