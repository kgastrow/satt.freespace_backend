import { useNavigation } from '@/hooks/useNavigation'
import { NavRenderer } from '@/components/navigation'

interface AdminSidebarProps {
  onNavigate?: () => void
}

/**
 * AdminSidebar component
 *
 * Renders the admin sidebar navigation using the data-driven navigation system.
 * Navigation items are filtered by user permissions via the useNavigation hook.
 */
export function AdminSidebar({ onNavigate }: AdminSidebarProps) {
  const { sections } = useNavigation('admin-sidebar')

  return <NavRenderer sections={sections} onItemClick={onNavigate} variant="admin" />
}
