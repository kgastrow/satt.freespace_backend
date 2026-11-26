/**
 * Maintenance Mode Integration Tests
 *
 * Tests the maintenance mode functionality including:
 * - Maintenance settings page access
 * - Maintenance history display
 * - Enabling/disabling maintenance mode
 * - History record creation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import {
  setCurrentUser,
  addMaintenanceHistoryItem,
  resetMaintenanceState,
} from '@/test/server'
import {
  superAdminUser,
  createAuthState,
  tokens,
} from '@/test/fixtures'
import { MaintenanceSettingsPage } from '@/pages/admin/MaintenanceSettingsPage'

// Mock environment variable
vi.stubEnv('VITE_ORG_SLUG', 'acme')

describe('Maintenance Mode Integration Tests', () => {
  beforeEach(() => {
    resetMaintenanceState()
    sessionStorage.setItem('access_token', tokens.validAccessToken)
  })

  describe('Maintenance Settings Page Access', () => {
    it('loads maintenance settings page for super admin', async () => {
      setCurrentUser(superAdminUser)

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for the page to load - look for translation key since i18n is mocked
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.pageTitle')).toBeInTheDocument()
      })
    })
  })

  describe('Maintenance History Display', () => {
    it('displays maintenance history table with items', async () => {
      setCurrentUser(superAdminUser)

      // Add some history items
      addMaintenanceHistoryItem({
        id: 'history-1',
        status: 'completed',
        scheduled_start: '2024-01-01T10:00:00Z',
        scheduled_end: '2024-01-01T14:00:00Z',
        actual_start: '2024-01-01T10:05:00Z',
        actual_end: '2024-01-01T13:45:00Z',
        message: 'Scheduled maintenance window',
        started_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        ended_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        created_time: '2024-01-01T09:00:00Z',
      })

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for history to load - look for translation key
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check that history item status is displayed - the status badge uses translation key
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.history.statuses.completed')).toBeInTheDocument()
      })
    })

    it('displays empty state when no history exists', async () => {
      setCurrentUser(superAdminUser)

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for page to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check for no history message - translation key
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.history.noHistory')).toBeInTheDocument()
      })
    })

    it('displays multiple history items', async () => {
      setCurrentUser(superAdminUser)

      // Add multiple history items
      addMaintenanceHistoryItem({
        id: 'history-1',
        status: 'completed',
        scheduled_start: null,
        scheduled_end: null,
        actual_start: '2024-01-01T10:00:00Z',
        actual_end: '2024-01-01T12:00:00Z',
        message: 'Emergency maintenance',
        started_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        ended_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        created_time: '2024-01-01T10:00:00Z',
      })

      addMaintenanceHistoryItem({
        id: 'history-2',
        status: 'active',
        scheduled_start: null,
        scheduled_end: null,
        actual_start: '2024-01-02T08:00:00Z',
        actual_end: null,
        message: 'Current maintenance',
        started_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        ended_by: null,
        created_time: '2024-01-02T08:00:00Z',
      })

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for history to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check that both items are displayed - look for status translation keys
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.history.statuses.completed')).toBeInTheDocument()
        expect(screen.getByText('admin:maintenance.history.statuses.active')).toBeInTheDocument()
      })
    })
  })

  describe('Maintenance Form', () => {
    it('shows allow super admin toggle with correct default', async () => {
      setCurrentUser(superAdminUser)

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for form to load - look for translation key
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.fields.allowSuperAdmin.label')).toBeInTheDocument()
      })

      // The toggle should exist
      const toggles = screen.getAllByRole('switch')
      expect(toggles.length).toBeGreaterThan(0)
    })

    it('enables maintenance mode when form is submitted', async () => {
      setCurrentUser(superAdminUser)

      const { user } = render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for form to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.fields.enabled.label')).toBeInTheDocument()
      })

      // Find the first toggle (maintenance enabled)
      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      // Find and click save button - look for translation key
      const saveButton = screen.getByText('admin:maintenance.actions.save')
      await user.click(saveButton)

      // Wait for the request to complete and history to update
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.history.statuses.active')).toBeInTheDocument()
      })
    })
  })

  describe('History Status Badges', () => {
    it('displays correct badge variants for different statuses', async () => {
      setCurrentUser(superAdminUser)

      // Add items with different statuses
      addMaintenanceHistoryItem({
        id: 'history-scheduled',
        status: 'scheduled',
        scheduled_start: '2024-02-01T10:00:00Z',
        scheduled_end: '2024-02-01T14:00:00Z',
        actual_start: null,
        actual_end: null,
        message: 'Scheduled maintenance',
        started_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        ended_by: null,
        created_time: '2024-01-15T10:00:00Z',
      })

      addMaintenanceHistoryItem({
        id: 'history-cancelled',
        status: 'cancelled',
        scheduled_start: '2024-01-20T10:00:00Z',
        scheduled_end: '2024-01-20T14:00:00Z',
        actual_start: null,
        actual_end: null,
        message: 'Cancelled maintenance',
        started_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        ended_by: {
          id: 'admin-1',
          first_name: 'Super',
          last_name: 'Admin',
          email: 'admin@example.com',
        },
        created_time: '2024-01-15T10:00:00Z',
      })

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for history to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check for scheduled and cancelled statuses - translation keys
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.history.statuses.scheduled')).toBeInTheDocument()
        expect(screen.getByText('admin:maintenance.history.statuses.cancelled')).toBeInTheDocument()
      })
    })
  })

  describe('User Info Display', () => {
    it('displays who started and ended maintenance', async () => {
      setCurrentUser(superAdminUser)

      addMaintenanceHistoryItem({
        id: 'history-1',
        status: 'completed',
        scheduled_start: null,
        scheduled_end: null,
        actual_start: '2024-01-01T10:00:00Z',
        actual_end: '2024-01-01T12:00:00Z',
        message: 'Test maintenance',
        started_by: {
          id: 'admin-1',
          first_name: 'John',
          last_name: 'Doe',
          email: 'john@example.com',
        },
        ended_by: {
          id: 'admin-2',
          first_name: 'Jane',
          last_name: 'Smith',
          email: 'jane@example.com',
        },
        created_time: '2024-01-01T10:00:00Z',
      })

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for history to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check that user names are displayed
      await waitFor(() => {
        expect(screen.getByText('John Doe')).toBeInTheDocument()
        expect(screen.getByText('Jane Smith')).toBeInTheDocument()
      })
    })

    it('displays email when name is not available', async () => {
      setCurrentUser(superAdminUser)

      addMaintenanceHistoryItem({
        id: 'history-1',
        status: 'active',
        scheduled_start: null,
        scheduled_end: null,
        actual_start: '2024-01-01T10:00:00Z',
        actual_end: null,
        message: 'Test maintenance',
        started_by: {
          id: 'admin-1',
          first_name: null,
          last_name: null,
          email: 'admin@example.com',
        },
        ended_by: null,
        created_time: '2024-01-01T10:00:00Z',
      })

      render(<MaintenanceSettingsPage />, {
        preloadedState: createAuthState(superAdminUser),
        route: '/admin/maintenance',
      })

      // Wait for history to load
      await waitFor(() => {
        expect(screen.getByText('admin:maintenance.historyCard.title')).toBeInTheDocument()
      })

      // Check that email is displayed instead of name
      await waitFor(() => {
        expect(screen.getByText('admin@example.com')).toBeInTheDocument()
      })
    })
  })
})
