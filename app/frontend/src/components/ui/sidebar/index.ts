"use client"

// Re-export everything for backward compatibility
export { SidebarProvider, useSidebar } from "./SidebarContext"
export { Sidebar } from "./Sidebar"
export { SidebarTrigger, SidebarRail } from "./SidebarTrigger"
export {
  SidebarInset,
  SidebarHeader,
  SidebarFooter,
  SidebarSeparator,
  SidebarInput,
} from "./SidebarLayout"
export { SidebarContent } from "./SidebarContent"
export {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupAction,
  SidebarGroupContent,
} from "./SidebarGroup"
export {
  sidebarMenuButtonVariants,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuSkeleton,
} from "./SidebarMenu"
export {
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
} from "./SidebarMenuSub"

// Re-export types for consumers who need them
export type {
  SidebarContextProps,
  SidebarProviderProps,
  SidebarProps,
  SidebarState,
  SidebarSide,
  SidebarVariant,
  SidebarCollapsible,
} from "./types"
