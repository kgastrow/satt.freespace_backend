import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { NotificationBell } from './NotificationBell'
import type { InAppNotification } from '@/types/in-app-notification'

// Mock the API hooks
vi.mock('@/features/in-app-notifications/inAppNotificationsApi', () => ({
  useGetInAppNotificationsQuery: vi.fn(() => ({ isFetching: false })),
  useGetUnreadCountQuery: vi.fn(() => ({})),
  useMarkAsReadMutation: vi.fn(() => [vi.fn().mockReturnValue({ unwrap: vi.fn() })]),
  useMarkAllAsReadMutation: vi.fn(() => [vi.fn().mockReturnValue({ unwrap: vi.fn() })]),
  useDismissNotificationsMutation: vi.fn(() => [vi.fn().mockReturnValue({ unwrap: vi.fn() })]),
  inAppNotificationsApi: {
    endpoints: {
      getInAppNotifications: { matchFulfilled: vi.fn(), matchPending: vi.fn(), matchRejected: vi.fn() },
      getUnreadCount: { matchFulfilled: vi.fn() },
      markAsRead: { matchFulfilled: vi.fn() },
      markAllAsRead: { matchFulfilled: vi.fn() },
      dismissNotifications: { matchFulfilled: vi.fn() },
    },
  },
}))

const mockNotification: InAppNotification = {
  id: 'notif-1',
  title: 'Test Notification',
  body: 'This is a test notification body',
  link: '/dashboard',
  category_id: 'cat-1',
  read_time: null,
  created_time: '2024-01-01T00:00:00Z',
}

const mockReadNotification: InAppNotification = {
  id: 'notif-2',
  title: 'Read Notification',
  body: 'This notification has been read',
  link: '/settings',
  category_id: 'cat-1',
  read_time: '2024-01-01T01:00:00Z',
  created_time: '2024-01-01T00:30:00Z',
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Bell Button', () => {
    it('renders the notification bell button', () => {
      render(<NotificationBell />)

      expect(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      ).toBeInTheDocument()
    })

    it('shows unread count badge when there are unread notifications', () => {
      render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 5,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('shows 99+ when unread count exceeds 99', () => {
      render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [],
            unreadCount: 150,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      expect(screen.getByText('99+')).toBeInTheDocument()
    })

    it('does not show badge when unread count is 0', () => {
      render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [],
            unreadCount: 0,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })
  })

  describe('Panel Interaction', () => {
    it('opens notification panel when bell is clicked', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(screen.getByText('common:notifications.title')).toBeInTheDocument()
      })
    })

    it('shows empty state when no notifications', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [],
            unreadCount: 0,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(screen.getByText('common:notifications.empty')).toBeInTheDocument()
      })
    })

    it('shows loading skeletons while loading', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [],
            unreadCount: 0,
            isLoading: true,
            hasMore: true,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        // Check for skeletons (they have animate-pulse class)
        const skeletons = document.querySelectorAll('[class*="animate-pulse"]')
        expect(skeletons.length).toBeGreaterThan(0)
      })
    })

    it('displays notifications in the panel', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification, mockReadNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(screen.getByText('Test Notification')).toBeInTheDocument()
        expect(screen.getByText('Read Notification')).toBeInTheDocument()
      })
    })

    it('shows mark all as read button when there are unread notifications', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /common:notifications.markAllRead/i })
        ).toBeInTheDocument()
      })
    })

    it('does not show mark all as read button when all notifications are read', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockReadNotification],
            unreadCount: 0,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(screen.getByText('common:notifications.title')).toBeInTheDocument()
      })

      expect(
        screen.queryByRole('button', { name: /common:notifications.markAllRead/i })
      ).not.toBeInTheDocument()
    })

    it('shows load more button when hasMore is true', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: true,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /common:notifications.loadMore/i })
        ).toBeInTheDocument()
      })
    })
  })

  describe('NotificationItem', () => {
    it('visually distinguishes unread notifications', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        // Unread notification should have the unread indicator
        expect(
          screen.getByLabelText('common:notifications.unread')
        ).toBeInTheDocument()
      })
    })

    it('shows notification body preview', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        expect(
          screen.getByText('This is a test notification body')
        ).toBeInTheDocument()
      })
    })

    it('shows dismiss button on hover', async () => {
      const { user } = render(<NotificationBell />, {
        preloadedState: {
          inAppNotifications: {
            notifications: [mockNotification],
            unreadCount: 1,
            isLoading: false,
            hasMore: false,
            panelOpen: false,
            pendingWebSocketCount: 0,
          },
        },
      })

      await user.click(
        screen.getByRole('button', { name: /common:notifications.openPanel/i })
      )

      await waitFor(() => {
        // The dismiss button exists but may be hidden (opacity-0)
        expect(
          screen.getByRole('button', { name: /common:notifications.dismiss/i })
        ).toBeInTheDocument()
      })
    })
  })
})
