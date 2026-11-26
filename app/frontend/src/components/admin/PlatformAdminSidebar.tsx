import { useNavigation } from '@/hooks/useNavigation'
import { NavRenderer } from '@/components/navigation'

interface PlatformAdminSidebarProps {
  onNavigate?: () => void
}

/**
 * PlatformAdminSidebar component
 *
 * Renders the platform admin sidebar navigation using the data-driven navigation system.
 * Platform admin navigation does not use permissions filtering (super admin only).
 */
export function PlatformAdminSidebar({ onNavigate }: PlatformAdminSidebarProps) {
  const { sections } = useNavigation('platform-admin-sidebar')

  return <NavRenderer sections={sections} onItemClick={onNavigate} variant="platform-admin" />
}
