import { toast as sonnerToast, type ExternalToast } from 'sonner'
import { Bell, Shield, FileIcon } from 'lucide-react'

/**
 * Toast categories that determine the icon displayed.
 * - notification: Bell icon for in-app notifications
 * - auth: Shield icon for authentication-related messages
 * - file: File icon for file operations
 * - undefined: Uses the toast type's default icon
 */
export type ToastCategory = 'notification' | 'auth' | 'file'

interface ToastOptions extends ExternalToast {
  category?: ToastCategory
}

const categoryIcons: Record<ToastCategory, React.ReactNode> = {
  notification: <Bell className="size-4" />,
  auth: <Shield className="size-4" />,
  file: <FileIcon className="size-4" />,
}

function getIconForCategory(category?: ToastCategory): React.ReactNode | undefined {
  return category ? categoryIcons[category] : undefined
}

/**
 * Toast utility with category support.
 * Categories determine the icon displayed in the toast.
 *
 * @example
 * // With category (custom icon)
 * toast.success('Logged in', { category: 'auth' })
 *
 * // Without category (default icon for type)
 * toast.success('Settings saved')
 */
export const toast = {
  success: (message: string, options?: ToastOptions) => {
    const { category, ...rest } = options ?? {}
    const icon = getIconForCategory(category)
    return sonnerToast.success(message, { ...rest, ...(icon && { icon }) })
  },

  error: (message: string, options?: ToastOptions) => {
    const { category, ...rest } = options ?? {}
    const icon = getIconForCategory(category)
    return sonnerToast.error(message, { ...rest, ...(icon && { icon }) })
  },

  info: (message: string, options?: ToastOptions) => {
    const { category, ...rest } = options ?? {}
    const icon = getIconForCategory(category)
    return sonnerToast.info(message, { ...rest, ...(icon && { icon }) })
  },

  warning: (message: string, options?: ToastOptions) => {
    const { category, ...rest } = options ?? {}
    const icon = getIconForCategory(category)
    return sonnerToast.warning(message, { ...rest, ...(icon && { icon }) })
  },

  message: (message: string, options?: ToastOptions) => {
    const { category, ...rest } = options ?? {}
    const icon = getIconForCategory(category)
    return sonnerToast.message(message, { ...rest, ...(icon && { icon }) })
  },

  loading: (message: string, options?: ExternalToast) => {
    return sonnerToast.loading(message, options)
  },

  dismiss: (toastId?: string | number) => {
    return sonnerToast.dismiss(toastId)
  },
}
