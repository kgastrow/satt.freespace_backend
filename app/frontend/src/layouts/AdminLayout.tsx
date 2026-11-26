import { Outlet } from 'react-router-dom'

/**
 * Layout wrapper for admin pages
 * Provides consistent structure for admin sections
 */
export function AdminLayout() {
  return (
    <div className="space-y-6">
      <Outlet />
    </div>
  )
}
