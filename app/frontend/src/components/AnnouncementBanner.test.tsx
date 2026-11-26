/**
 * AnnouncementBanner Component Tests
 *
 * Tests the AnnouncementBanner component rendering, navigation, dismissal, and CTA behavior
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'
import { render, createTestStore, type TestStore } from '@/test/utils'
import { AnnouncementBanner } from '@/components/AnnouncementBanner'
import { tokens } from '@/test/fixtures'
import type { Announcement } from '@/types/announcement'

// Mock announcements
const mockAnnouncements: Announcement[] = [
  {
    id: 'ann-1',
    organization_id: 'org-123',
    title: 'Critical Update',
    body: 'This is a critical announcement',
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
    created_by_id: 'user-1',
    created_time: '2026-01-01T00:00:00Z',
    updated_time: null,
    is_platform_wide: false,
  },
  {
    id: 'ann-2',
    organization_id: null,
    title: 'Platform Announcement',
    body: 'Platform-wide announcement',
    priority: 'high',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: 'Learn More',
    cta_url: '/updates',
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: 'default',
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
    title: 'Non-dismissible Announcement',
    body: 'This announcement cannot be dismissed',
    priority: 'normal',
    background_color: null,
    text_color: null,
    featured_image_url: null,
    cta_text: 'Accept',
    cta_url: '/terms',
    cta_dismisses: true,
    cta_button_color: null,
    cta_button_variant: 'default',
    is_dismissible: false,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-12-31T23:59:59Z',
    created_by_id: 'user-1',
    created_time: '2026-01-03T00:00:00Z',
    updated_time: null,
    is_platform_wide: false,
  },
]

describe('AnnouncementBanner', () => {
  let store: TestStore

  beforeEach(() => {
    server.resetHandlers()
  })

  describe('when no announcements', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [],
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: [] })
        })
      )
    })

    it('does not render when no announcements', () => {
      const { container } = render(<AnnouncementBanner />, { store })
      expect(container.firstChild).toBeNull()
    })
  })

  describe('when announcements exist', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: mockAnnouncements,
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: mockAnnouncements })
        })
      )
    })

    // Note: Announcements are sorted: non-dismissible first, then by priority (critical > high > normal > low)
    // So the order is: Non-dismissible Announcement (normal, non-dismissible) -> Critical Update -> Platform Announcement
    // Banner shows "title: body" format with title in bold
    it('renders the banner with announcement title and body', async () => {
      render(<AnnouncementBanner />, { store })

      // First announcement after sorting is the non-dismissible one
      // Title is bold, followed by ": body"
      await waitFor(() => {
        expect(screen.getByText('Non-dismissible Announcement')).toBeInTheDocument()
        expect(screen.getByText(/This announcement cannot be dismissed/)).toBeInTheDocument()
      })
    })

    it('shows navigation controls when multiple announcements', async () => {
      render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        // Should show count like "1/3"
        expect(screen.getByText('1/3')).toBeInTheDocument()
      })

      // Should have prev/next buttons
      expect(screen.getByLabelText(/previous/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/next/i)).toBeInTheDocument()
    })

    it('navigates to next announcement on next click', async () => {
      const { user } = render(<AnnouncementBanner />, { store })

      // First announcement after sorting - title is in <strong> tag
      await waitFor(() => {
        expect(screen.getByText('Non-dismissible Announcement')).toBeInTheDocument()
      })

      const nextButton = screen.getByLabelText(/next/i)
      await user.click(nextButton)

      // Next in sorted order is Critical Update
      await waitFor(() => {
        expect(screen.getByText('Critical Update')).toBeInTheDocument()
        expect(screen.getByText('2/3')).toBeInTheDocument()
      })
    })

    it('navigates to previous announcement on prev click', async () => {
      const { user } = render(<AnnouncementBanner />, { store })

      // First announcement after sorting - title is in <strong> tag
      await waitFor(() => {
        expect(screen.getByText('Non-dismissible Announcement')).toBeInTheDocument()
      })

      const prevButton = screen.getByLabelText(/previous/i)
      await user.click(prevButton)

      // Should wrap around to last announcement (Platform Announcement)
      await waitFor(() => {
        expect(screen.getByText('Platform Announcement')).toBeInTheDocument()
        expect(screen.getByText('3/3')).toBeInTheDocument()
      })
    })
  })

  describe('dismissal behavior', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [mockAnnouncements[0]], // Only dismissible announcement
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: [mockAnnouncements[0]] })
        }),
        http.post(`${API_BASE}/announcements/:id/dismiss`, () => {
          return HttpResponse.json({
            message: 'Announcement dismissed successfully',
            announcement_id: 'ann-1',
          })
        })
      )
    })

    it('shows dismiss button for dismissible announcements', async () => {
      render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        const dismissButton = screen.getByLabelText(/dismiss/i)
        expect(dismissButton).toBeInTheDocument()
      })
    })

    it('dismisses announcement on button click', async () => {
      const { user } = render(<AnnouncementBanner />, { store })

      const dismissButton = await waitFor(() => {
        const btn = screen.getByLabelText(/dismiss/i)
        expect(btn).toBeInTheDocument()
        return btn
      })

      await user.click(dismissButton)

      await waitFor(() => {
        expect(screen.queryByText('Critical Update')).not.toBeInTheDocument()
      })
    })
  })

  describe('click to open dialog', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [mockAnnouncements[1]], // Platform announcement with CTA
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: [mockAnnouncements[1]] })
        }),
        http.post(`${API_BASE}/announcements/:id/dismiss`, () => {
          return HttpResponse.json({
            message: 'Announcement dismissed successfully',
            announcement_id: 'ann-2',
          })
        })
      )
    })

    it('opens full announcement dialog when clicking banner', async () => {
      const { user } = render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        expect(screen.getByText('Platform Announcement')).toBeInTheDocument()
      })

      // Click the banner text area to open dialog
      const banner = screen.getByRole('button', { name: /viewDetails/i })
      await user.click(banner)

      // Dialog should show full announcement with CTA
      await waitFor(() => {
        expect(screen.getByText('Learn More')).toBeInTheDocument()
      })
    })
  })

  describe('non-dismissible announcements', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [mockAnnouncements[2]], // Non-dismissible announcement
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: [mockAnnouncements[2]] })
        })
      )
    })

    it('does not show dismiss button for non-dismissible announcements', async () => {
      render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        expect(screen.getByText('Non-dismissible Announcement')).toBeInTheDocument()
      })

      expect(screen.queryByLabelText(/dismiss/i)).not.toBeInTheDocument()
    })

    it('shows CTA in dialog for non-dismissible announcements', async () => {
      const { user } = render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        expect(screen.getByText('Non-dismissible Announcement')).toBeInTheDocument()
      })

      // Click the banner text area to open dialog
      const banner = screen.getByRole('button', { name: /viewDetails/i })
      await user.click(banner)

      // Dialog should show CTA button
      await waitFor(() => {
        expect(screen.getByText('Accept')).toBeInTheDocument()
      })
    })
  })

  describe('single announcement', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [mockAnnouncements[0]],
          isLoading: false,
          locallyDismissedIds: new Set(),
        },
      })

      server.use(
        http.get(`${API_BASE}/announcements/active`, () => {
          return HttpResponse.json({ announcements: [mockAnnouncements[0]] })
        })
      )
    })

    it('does not show navigation controls for single announcement', async () => {
      render(<AnnouncementBanner />, { store })

      await waitFor(() => {
        expect(screen.getByText('Critical Update')).toBeInTheDocument()
      })

      // Should not have prev/next buttons or count
      expect(screen.queryByLabelText(/previous/i)).not.toBeInTheDocument()
      expect(screen.queryByLabelText(/next/i)).not.toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: 'user-123',
            email: 'user@example.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: false,
          },
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        announcements: {
          announcements: [],
          isLoading: true,
          locallyDismissedIds: new Set(),
        },
      })
    })

    it('does not render when loading', () => {
      const { container } = render(<AnnouncementBanner />, { store })
      expect(container.firstChild).toBeNull()
    })
  })
})
