import { useEffect, useRef } from 'react'
import { useAppSelector } from '@/store/hooks'
import { useGetMaintenanceStatusQuery } from '@/features/maintenance/maintenanceApi'
import { MaintenancePage } from '@/pages/MaintenancePage'

interface MaintenanceProviderProps {
  children: React.ReactNode
}

/**
 * MaintenanceProvider checks maintenance status and displays maintenance page when active.
 *
 * Data sources:
 * 1. RTK Query (initial fetch) - updates Redux state via extraReducers
 * 2. WebSocket messages - updates Redux state in real-time
 *
 * Both sources update the same Redux state (maintenance slice), so we only need
 * to read from Redux state. The RTK Query also provides isLoading for initial load.
 *
 * Super admins with allow_super_admin=true can bypass maintenance mode.
 */
export function MaintenanceProvider({ children }: MaintenanceProviderProps) {
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAppSelector((state) => state.auth)
  const wasInMaintenanceRef = useRef(false)

  // Get maintenance state from Redux
  // This is updated by both RTK Query (extraReducers) and WebSocket (useMaintenanceWebSocket)
  const { isMaintenanceActive } = useAppSelector((state) => state.maintenance)

  // Fetch maintenance status on mount - triggers Redux updates via extraReducers
  // Real-time updates come via WebSocket. We need isLoading and allow_super_admin from the response
  const { data: maintenanceStatus, isLoading } = useGetMaintenanceStatusQuery()

  // Check if the current user can bypass maintenance
  const canBypassMaintenance =
    isAuthenticated &&
    user?.is_admin &&
    maintenanceStatus?.allow_super_admin === true

  // Track maintenance state changes to trigger page reload when it ends.
  // Only track after auth has loaded — otherwise a transient state where
  // maintenance status resolves before auth would falsely mark the user as
  // having seen the maintenance page, causing an unwanted redirect later.
  useEffect(() => {
    if (isAuthLoading) return

    if (isMaintenanceActive && !canBypassMaintenance) {
      wasInMaintenanceRef.current = true
    } else if (wasInMaintenanceRef.current && !isMaintenanceActive) {
      // Maintenance has ended, reload the page to restore WebSocket
      window.location.href = '/'
    }
  }, [isMaintenanceActive, canBypassMaintenance, isAuthLoading])

  // While loading maintenance status or auth, don't render children to prevent flash.
  // Auth must finish loading before we evaluate canBypassMaintenance, otherwise admin
  // users get briefly shown the public MaintenancePage while their profile loads.
  if (isLoading || isAuthLoading) {
    return null
  }

  // If maintenance is active and user cannot bypass, show maintenance page
  if (isMaintenanceActive && !canBypassMaintenance) {
    return <MaintenancePage />
  }

  return <>{children}</>
}
