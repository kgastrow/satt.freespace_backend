/**
 * Notification System Integration Tests
 *
 * Tests the notification functionality including:
 * - Send notification and history update
 * - Template creation and usage
 * - Bulk notification lifecycle
 * - User preferences application
 */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@/test/utils'
import { server, setCurrentUser, API_BASE } from '@/test/server'
import {
  adminUser,
  createAuthState,
  notifications,
  userNotificationPreference,
} from '@/test/fixtures'
import type { NotificationChannel } from '@/features/notifications/notificationsApi'
import {
  useGetNotificationsQuery,
  useSendNotificationMutation,
  useGetTemplatesQuery,
  useCreateTemplateMutation,
  useGetUserPreferencesQuery,
  useUpdateUserPreferencesMutation,
  useCreateBulkNotificationMutation,
  useGetBulkNotificationQuery,
} from '@/features/notifications/notificationsApi'

// Mock the toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Test component for notification history
function NotificationHistory() {
  const { data, isLoading, error } = useGetNotificationsQuery({})

  if (isLoading) return <div>Loading...</div>
  if (error) return <div>Error loading notifications</div>

  return (
    <div>
      <h2>Notification History</h2>
      <ul>
        {data?.items.map((notif) => (
          <li key={notif.id} data-testid={`notif-${notif.id}`}>
            <span data-testid={`notif-${notif.id}-channel`}>{notif.channel}</span>
            <span data-testid={`notif-${notif.id}-status`}>{notif.status}</span>
            <span data-testid={`notif-${notif.id}-recipient`}>{notif.recipient}</span>
          </li>
        ))}
      </ul>
      <div data-testid="notif-count">Total: {data?.total}</div>
    </div>
  )
}

// Test component for templates
function TemplateList() {
  const { data, isLoading, error } = useGetTemplatesQuery({})

  if (isLoading) return <div>Loading...</div>
  if (error) return <div>Error loading templates</div>

  return (
    <div>
      <h2>Templates</h2>
      <ul>
        {data?.items.map((template) => (
          <li key={template.id} data-testid={`template-${template.id}`}>
            <span data-testid={`template-${template.id}-name`}>{template.name}</span>
            <span data-testid={`template-${template.id}-channel`}>{template.channel}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Test component for user preferences
function UserPreferences() {
  const { data, isLoading, error } = useGetUserPreferencesQuery()

  if (isLoading) return <div>Loading...</div>
  if (error) return <div>Error loading preferences</div>

  return (
    <div>
      <h2>Notification Preferences</h2>
      <div data-testid="email-enabled">{data?.email_enabled ? 'Email: On' : 'Email: Off'}</div>
      <div data-testid="sms-enabled">{data?.sms_enabled ? 'SMS: On' : 'SMS: Off'}</div>
      <div data-testid="quiet-hours">{data?.quiet_hours_enabled ? 'Quiet Hours: On' : 'Quiet Hours: Off'}</div>
      {data?.quiet_hours_enabled && (
        <div data-testid="quiet-hours-time">
          {data.quiet_hours_start} - {data.quiet_hours_end}
        </div>
      )}
    </div>
  )
}

describe('Notification System Integration Tests', () => {
  describe('Notification History', () => {
    it('displays notification history', async () => {
      setCurrentUser(adminUser)

      render(<NotificationHistory />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Should display notifications
      expect(screen.getByTestId('notif-notif-1')).toBeInTheDocument()
      expect(screen.getByTestId('notif-notif-2')).toBeInTheDocument()
      expect(screen.getByTestId('notif-count')).toHaveTextContent('Total: 2')
    })

    it('shows notification channel and status', async () => {
      setCurrentUser(adminUser)

      render(<NotificationHistory />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Check first notification
      expect(screen.getByTestId('notif-notif-1-channel')).toHaveTextContent('email')
      expect(screen.getByTestId('notif-notif-1-status')).toHaveTextContent('delivered')

      // Check second notification
      expect(screen.getByTestId('notif-notif-2-channel')).toHaveTextContent('sms')
      expect(screen.getByTestId('notif-notif-2-status')).toHaveTextContent('sent')
    })

    it('filters notifications by channel', async () => {
      let lastChannel: string | null = null

      server.use(
        http.get(`${API_BASE}/notifications`, ({ request }) => {
          const url = new URL(request.url)
          // SDL format: filter[channel]=email
          lastChannel = url.searchParams.get('filter[channel]')

          const filtered = lastChannel
            ? notifications.filter((n) => n.channel === lastChannel)
            : notifications

          return HttpResponse.json({
            items: filtered,
            total: filtered.length,
            limit: 50,
            offset: 0,
          })
        })
      )

      // Component that filters by channel
      function FilteredNotifications({ channel }: { channel?: NotificationChannel }) {
        const { data, isLoading } = useGetNotificationsQuery({ channel })

        if (isLoading) return <div>Loading...</div>

        return (
          <div data-testid="filtered-count">Count: {data?.items.length}</div>
        )
      }

      setCurrentUser(adminUser)

      render(<FilteredNotifications channel="email" />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(lastChannel).toBe('email')
      })
    })
  })

  describe('Send Notification', () => {
    it('sends notification and returns result', async () => {
      let sendCalled = false
      let sentData: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/notifications/send`, async ({ request }) => {
          sendCalled = true
          sentData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            message: 'Notification sent successfully',
            notification: {
              id: 'new-notif',
              channel: sentData.channel,
              recipient: 'admin@acme.com',
              status: 'pending',
              provider_message_id: null,
              created_time: new Date().toISOString(),
            },
          })
        })
      )

      // Component that sends notifications
      function SendNotification() {
        const [send, { isLoading, data }] = useSendNotificationMutation()

        const handleSend = async () => {
          await send({
            channel: 'email',
            user_id: 'user-2',
            subject: 'Test',
            content: 'Test content',
            is_urgent: false,
          })
        }

        return (
          <div>
            <button onClick={handleSend} disabled={isLoading}>
              {isLoading ? 'Sending...' : 'Send'}
            </button>
            {data && <div data-testid="sent-result">Sent!</div>}
          </div>
        )
      }

      setCurrentUser(adminUser)

      const { user } = render(<SendNotification />, {
        preloadedState: createAuthState(adminUser),
      })

      await user.click(screen.getByRole('button', { name: 'Send' }))

      await waitFor(() => {
        expect(sendCalled).toBe(true)
      })

      expect(sentData).toMatchObject({
        channel: 'email',
        user_id: 'user-2',
      })
    })

    it('sends notification using template', async () => {
      let sentData: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/notifications/send`, async ({ request }) => {
          sentData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            message: 'Notification sent',
            notification: {
              id: 'new-notif',
              channel: 'email',
              template_id: 'template-1',
              status: 'pending',
              created_time: new Date().toISOString(),
            },
          })
        })
      )

      // Component that sends with template
      function SendWithTemplate() {
        const [send] = useSendNotificationMutation()

        const handleSend = async () => {
          await send({
            channel: 'email',
            user_id: 'user-1',
            template_code: 'welcome',
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            template_variables: { first_name: 'John', org_name: 'Acme' } as any,
            is_urgent: false,
          })
        }

        return <button onClick={handleSend}>Send with Template</button>
      }

      setCurrentUser(adminUser)

      const { user } = render(<SendWithTemplate />, {
        preloadedState: createAuthState(adminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(sentData).toMatchObject({
          template_code: 'welcome',
          template_variables: { first_name: 'John', org_name: 'Acme' },
        })
      })
    })
  })

  describe('Template Management', () => {
    it('displays template list', async () => {
      setCurrentUser(adminUser)

      render(<TemplateList />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('template-template-1')).toBeInTheDocument()
      expect(screen.getByTestId('template-template-1-name')).toHaveTextContent('Welcome Email')
      expect(screen.getByTestId('template-template-1-channel')).toHaveTextContent('email')
    })

    it('creates new template', async () => {
      let createCalled = false
      let createdData: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/notifications/templates`, async ({ request }) => {
          createCalled = true
          createdData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            message: 'Template created',
            template: {
              id: 'new-template',
              ...createdData,
              organization_id: 'org-1',
              created_time: new Date().toISOString(),
            },
          })
        })
      )

      // Component that creates templates
      function CreateTemplate() {
        const [create, { isLoading }] = useCreateTemplateMutation()

        const handleCreate = async () => {
          await create({
            code: 'new_template',
            name: 'New Template',
            channel: 'email',
            body_text: 'Hello {{name}}!',
            is_active: true,
          })
        }

        return (
          <button onClick={handleCreate} disabled={isLoading}>
            Create Template
          </button>
        )
      }

      setCurrentUser(adminUser)

      const { user } = render(<CreateTemplate />, {
        preloadedState: createAuthState(adminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(createCalled).toBe(true)
      })

      expect(createdData).toMatchObject({
        code: 'new_template',
        name: 'New Template',
        channel: 'email',
      })
    })
  })

  describe('User Notification Preferences', () => {
    it('displays user preferences', async () => {
      setCurrentUser(adminUser)

      render(<UserPreferences />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('email-enabled')).toHaveTextContent('Email: On')
      expect(screen.getByTestId('sms-enabled')).toHaveTextContent('SMS: On')
      expect(screen.getByTestId('quiet-hours')).toHaveTextContent('Quiet Hours: On')
      expect(screen.getByTestId('quiet-hours-time')).toHaveTextContent('22:00 - 08:00')
    })

    it('updates user preferences', async () => {
      let updateCalled = false
      let updatedData: Record<string, unknown> | null = null

      server.use(
        http.put(`${API_BASE}/notifications/preferences`, async ({ request }) => {
          updateCalled = true
          updatedData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            message: 'Preferences updated',
            preferences: {
              ...userNotificationPreference,
              ...updatedData,
            },
          })
        })
      )

      // Component that updates preferences
      function UpdatePreferences() {
        const [update, { isLoading }] = useUpdateUserPreferencesMutation()

        const handleUpdate = async () => {
          await update({
            email_enabled: false,
            quiet_hours_enabled: false,
          })
        }

        return (
          <button onClick={handleUpdate} disabled={isLoading}>
            Update Preferences
          </button>
        )
      }

      setCurrentUser(adminUser)

      const { user } = render(<UpdatePreferences />, {
        preloadedState: createAuthState(adminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(updateCalled).toBe(true)
      })

      expect(updatedData).toMatchObject({
        email_enabled: false,
        quiet_hours_enabled: false,
      })
    })
  })

  describe('Bulk Notifications', () => {
    it('creates bulk notification', async () => {
      let createCalled = false
      let createdData: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/notifications/bulk`, async ({ request }) => {
          createCalled = true
          createdData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            message: 'Bulk notification created',
            bulk_notification: {
              id: 'bulk-1',
              name: createdData?.name,
              channel: createdData?.channel,
              status: 'pending',
              total_recipients: 10,
              sent_count: 0,
              failed_count: 0,
              created_time: new Date().toISOString(),
            },
          })
        })
      )

      // Component that creates bulk notification
      function CreateBulkNotification() {
        const [create, { isLoading, data }] = useCreateBulkNotificationMutation()

        const handleCreate = async () => {
          await create({
            name: 'Weekly Update',
            channel: 'email',
            template_code: 'weekly_update',
            recipient_filters: {
              role_ids: ['role-1'],
              verified_contact_only: true,
            },
          })
        }

        return (
          <div>
            <button onClick={handleCreate} disabled={isLoading}>
              Create Bulk
            </button>
            {data && <div data-testid="bulk-created">Created: {data.bulk_notification.id}</div>}
          </div>
        )
      }

      setCurrentUser(adminUser)

      const { user } = render(<CreateBulkNotification />, {
        preloadedState: createAuthState(adminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(createCalled).toBe(true)
      })

      expect(createdData).toMatchObject({
        name: 'Weekly Update',
        channel: 'email',
      })
    })

    it('tracks bulk notification status', async () => {
      let requestCount = 0

      server.use(
        http.get(`${API_BASE}/notifications/bulk/:id`, () => {
          requestCount++
          const status = requestCount < 3 ? 'processing' : 'completed'

          return HttpResponse.json({
            id: 'bulk-1',
            name: 'Test Bulk',
            channel: 'email',
            status,
            total_recipients: 10,
            sent_count: requestCount < 3 ? requestCount * 3 : 10,
            failed_count: 0,
            created_time: '2024-01-01T00:00:00Z',
          })
        })
      )

      // Component that displays bulk notification status
      function BulkNotificationStatus({ id }: { id: string }) {
        const { data, isLoading, refetch } = useGetBulkNotificationQuery(id)

        return (
          <div>
            {isLoading && <div>Loading...</div>}
            {data && (
              <>
                <div data-testid="bulk-status">{data.status}</div>
                <div data-testid="bulk-sent">{data.sent_count}/{data.total_recipients}</div>
                <button onClick={() => refetch()}>Refresh</button>
              </>
            )}
          </div>
        )
      }

      setCurrentUser(adminUser)

      const { user } = render(<BulkNotificationStatus id="bulk-1" />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Initial status should be processing
      expect(screen.getByTestId('bulk-status')).toHaveTextContent('processing')

      // Refresh to get updated status
      await user.click(screen.getByRole('button', { name: 'Refresh' }))

      await waitFor(() => {
        expect(requestCount).toBeGreaterThan(1)
      })
    })
  })

  describe('Notification Settings (Admin)', () => {
    it('displays organization notification settings', async () => {
      // Component that displays settings
      function NotificationSettingsDisplay() {
        const { data: prefs, isLoading } = useGetUserPreferencesQuery()

        if (isLoading) return <div>Loading...</div>

        return (
          <div>
            <div data-testid="email-status">{prefs?.email_enabled ? 'Enabled' : 'Disabled'}</div>
            <div data-testid="sms-status">{prefs?.sms_enabled ? 'Enabled' : 'Disabled'}</div>
          </div>
        )
      }

      setCurrentUser(adminUser)

      render(<NotificationSettingsDisplay />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('email-status')).toHaveTextContent('Enabled')
      expect(screen.getByTestId('sms-status')).toHaveTextContent('Enabled')
    })
  })
})
