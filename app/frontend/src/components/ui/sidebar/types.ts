import type { VariantProps } from "class-variance-authority"
import type { TooltipContent } from "@/components/ui/tooltip"

export type SidebarState = "expanded" | "collapsed"
export type SidebarSide = "left" | "right"
export type SidebarVariant = "sidebar" | "floating" | "inset"
export type SidebarCollapsible = "offcanvas" | "icon" | "none"

export interface SidebarContextProps {
  state: SidebarState
  open: boolean
  setOpen: (open: boolean) => void
  openMobile: boolean
  setOpenMobile: (open: boolean) => void
  isMobile: boolean
  toggleSidebar: () => void
}

export interface SidebarProviderProps extends React.ComponentProps<"div"> {
  defaultOpen?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export interface SidebarProps extends React.ComponentProps<"div"> {
  side?: SidebarSide
  variant?: SidebarVariant
  collapsible?: SidebarCollapsible
}

// Re-export variant types for external use
export type { VariantProps }

// Tooltip content type for SidebarMenuButton
export type TooltipContentProps = React.ComponentProps<typeof TooltipContent>
