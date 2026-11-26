# Sidebar Component Refactor Plan

**Status:** ✅ COMPLETED (2026-02-04)

## Overview

The sidebar component was 725 lines and has been split into `src/components/ui/sidebar/` with 11 modules. See `ai_docs/frontend/context/components.md` for current structure.

## Current State Analysis

### File Statistics
- **Total Lines:** 725
- **Total Components:** 22 components + 1 hook + 1 context
- **Exports:** 23 named exports

### Current Component Breakdown

| Component | Lines | Category |
|-----------|-------|----------|
| `SidebarContext` + `useSidebar` | 46-53 | Context/Hook |
| `SidebarProvider` | 55-148 | Provider |
| `Sidebar` | 150-250 | Core Container |
| `SidebarTrigger` | 252-276 | Controls |
| `SidebarRail` | 278-301 | Controls |
| `SidebarInset` | 303-315 | Layout |
| `SidebarInput` | 317-329 | Form Elements |
| `SidebarHeader` | 331-339 | Layout |
| `SidebarFooter` | 342-351 | Layout |
| `SidebarSeparator` | 353-365 | Layout |
| `SidebarContent` | 367-382 | Content |
| `SidebarGroup` | 384-393 | Group Components |
| `SidebarGroupLabel` | 395-414 | Group Components |
| `SidebarGroupAction` | 416-437 | Group Components |
| `SidebarGroupContent` | 439-451 | Group Components |
| `SidebarMenu` | 453-461 | Menu Components |
| `SidebarMenuItem` | 464-473 | Menu Components |
| `sidebarMenuButtonVariants` | 475-495 | Menu Components |
| `SidebarMenuButton` | 497-545 | Menu Components |
| `SidebarMenuAction` | 547-577 | Menu Components |
| `SidebarMenuBadge` | 579-599 | Menu Components |
| `SidebarMenuSkeleton` | 601-635 | Menu Components |
| `SidebarMenuSub` | 637-650 | Submenu Components |
| `SidebarMenuSubItem` | 652-664 | Submenu Components |
| `SidebarMenuSubButton` | 666-696 | Submenu Components |

---

## Proposed File Structure

```
app/frontend/src/components/ui/sidebar/
  index.ts              # Public exports (backward compatible)
  types.ts              # Type definitions
  constants.ts          # Configuration constants
  SidebarContext.tsx    # Context, hook, and provider
  Sidebar.tsx           # Main Sidebar component
  SidebarTrigger.tsx    # Trigger and Rail components
  SidebarLayout.tsx     # Layout components (Header, Footer, Inset, Separator)
  SidebarContent.tsx    # Content container
  SidebarGroup.tsx      # Group components (Group, Label, Action, Content)
  SidebarMenu.tsx       # Menu components (Menu, MenuItem, Button, Action, Badge, Skeleton)
  SidebarMenuSub.tsx    # Submenu components (Sub, SubItem, SubButton)
```

---

## Detailed File Specifications

### 1. `types.ts` - Type Definitions

**Purpose:** Centralize all TypeScript types for better maintainability.

**Contents:**
```typescript
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
```

**Estimated lines:** ~35

---

### 2. `constants.ts` - Configuration Constants

**Purpose:** Single source of truth for sidebar dimensions and keyboard shortcuts.

**Contents:**
```typescript
export const SIDEBAR_WIDTH = "16rem"
export const SIDEBAR_WIDTH_MOBILE = "18rem"
export const SIDEBAR_WIDTH_ICON = "3rem"
export const SIDEBAR_KEYBOARD_SHORTCUT = "b"
```

**Estimated lines:** ~5

---

### 3. `SidebarContext.tsx` - Context and Provider

**Purpose:** All context-related code including the provider component.

**Contents:**
- `SidebarContext` creation
- `useSidebar` hook
- `SidebarProvider` component

**Dependencies:**
```typescript
import * as React from "react"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { TooltipProvider } from "@/components/ui/tooltip"
import {
  SIDEBAR_WIDTH,
  SIDEBAR_WIDTH_ICON,
  SIDEBAR_KEYBOARD_SHORTCUT
} from "./constants"
import type { SidebarContextProps, SidebarProviderProps } from "./types"
```

**Exports:**
```typescript
export { SidebarContext, SidebarProvider, useSidebar }
```

**Estimated lines:** ~100

---

### 4. `Sidebar.tsx` - Main Sidebar Component

**Purpose:** The core sidebar container with desktop/mobile rendering logic.

**Contents:**
- `Sidebar` component (handles non-collapsible, mobile Sheet, desktop views)

**Dependencies:**
```typescript
import * as React from "react"
import { cn } from "@/lib/utils"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { useSidebar } from "./SidebarContext"
import { SIDEBAR_WIDTH_MOBILE } from "./constants"
import type { SidebarProps } from "./types"
```

**Exports:**
```typescript
export { Sidebar }
```

**Estimated lines:** ~100

---

### 5. `SidebarTrigger.tsx` - Trigger and Rail Components

**Purpose:** Interactive elements for toggling the sidebar.

**Contents:**
- `SidebarTrigger` component
- `SidebarRail` component

**Dependencies:**
```typescript
import * as React from "react"
import { PanelLeftIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { useSidebar } from "./SidebarContext"
```

**Exports:**
```typescript
export { SidebarTrigger, SidebarRail }
```

**Estimated lines:** ~50

---

### 6. `SidebarLayout.tsx` - Layout Components

**Purpose:** Structural layout components for sidebar sections.

**Contents:**
- `SidebarInset` component
- `SidebarHeader` component
- `SidebarFooter` component
- `SidebarSeparator` component
- `SidebarInput` component

**Dependencies:**
```typescript
import * as React from "react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
```

**Exports:**
```typescript
export { SidebarInset, SidebarHeader, SidebarFooter, SidebarSeparator, SidebarInput }
```

**Estimated lines:** ~65

---

### 7. `SidebarContent.tsx` - Content Container

**Purpose:** Scrollable content area for sidebar.

**Contents:**
- `SidebarContent` component

**Dependencies:**
```typescript
import * as React from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
```

**Exports:**
```typescript
export { SidebarContent }
```

**Estimated lines:** ~20

---

### 8. `SidebarGroup.tsx` - Group Components

**Purpose:** Components for organizing sidebar items into groups.

**Contents:**
- `SidebarGroup` component
- `SidebarGroupLabel` component
- `SidebarGroupAction` component
- `SidebarGroupContent` component

**Dependencies:**
```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cn } from "@/lib/utils"
```

**Exports:**
```typescript
export { SidebarGroup, SidebarGroupLabel, SidebarGroupAction, SidebarGroupContent }
```

**Estimated lines:** ~75

---

### 9. `SidebarMenu.tsx` - Menu Components

**Purpose:** Navigation menu components with interactive buttons.

**Contents:**
- `sidebarMenuButtonVariants` (CVA definition)
- `SidebarMenu` component
- `SidebarMenuItem` component
- `SidebarMenuButton` component
- `SidebarMenuAction` component
- `SidebarMenuBadge` component
- `SidebarMenuSkeleton` component

**Dependencies:**
```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useSidebar } from "./SidebarContext"
```

**Exports:**
```typescript
export {
  sidebarMenuButtonVariants,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuSkeleton
}
```

**Estimated lines:** ~180

---

### 10. `SidebarMenuSub.tsx` - Submenu Components

**Purpose:** Nested submenu navigation components.

**Contents:**
- `SidebarMenuSub` component
- `SidebarMenuSubItem` component
- `SidebarMenuSubButton` component

**Dependencies:**
```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cn } from "@/lib/utils"
```

**Exports:**
```typescript
export { SidebarMenuSub, SidebarMenuSubItem, SidebarMenuSubButton }
```

**Estimated lines:** ~65

---

### 11. `index.ts` - Public API (Backward Compatible)

**Purpose:** Re-export all components maintaining the same public API.

**Contents:**
```typescript
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
  SidebarInput
} from "./SidebarLayout"
export { SidebarContent } from "./SidebarContent"
export {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupAction,
  SidebarGroupContent
} from "./SidebarGroup"
export {
  sidebarMenuButtonVariants,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuSkeleton
} from "./SidebarMenu"
export {
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton
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
```

**Estimated lines:** ~45

---

## Import Changes for Consumers

### No Changes Required

The refactor maintains backward compatibility. Existing imports will continue to work:

```typescript
// This will still work - no changes needed
import {
  SidebarProvider,
  SidebarInset,
  useSidebar
} from '@/components/ui/sidebar'
```

The `@/components/ui/sidebar` path will now resolve to `@/components/ui/sidebar/index.ts` instead of `@/components/ui/sidebar.tsx`.

### Files Using Sidebar Components

These files will **NOT** need modification:

1. `/app/frontend/src/layouts/DashboardLayout.tsx`
2. `/app/frontend/src/components/AppSidebar.tsx`
3. `/app/frontend/src/components/navigation/NavRenderer.tsx`

---

## Migration Steps

### Phase 1: Create New Directory Structure
1. Create `/app/frontend/src/components/ui/sidebar/` directory
2. Create all new files with "use client" directive where needed

### Phase 2: Extract Code (in order)
1. Create `types.ts` with type definitions
2. Create `constants.ts` with constants
3. Create `SidebarContext.tsx` with context, hook, and provider
4. Create `Sidebar.tsx` with main component
5. Create `SidebarTrigger.tsx` with trigger and rail
6. Create `SidebarLayout.tsx` with layout components
7. Create `SidebarContent.tsx` with content component
8. Create `SidebarGroup.tsx` with group components
9. Create `SidebarMenu.tsx` with menu components
10. Create `SidebarMenuSub.tsx` with submenu components
11. Create `index.ts` with all exports

### Phase 3: Verification
1. Run `npm run build:only` to verify TypeScript compilation
2. Run `npm run test` to verify no regressions
3. Run `npm run lint` to verify code quality

### Phase 4: Cleanup
1. Delete `/app/frontend/src/components/ui/sidebar.tsx`
2. Commit changes with descriptive message

---

## Testing Checklist

### Automated Tests
- [ ] All existing tests pass without modification
- [ ] TypeScript compilation succeeds
- [ ] ESLint passes
- [ ] Build succeeds

### Manual Testing
- [ ] Sidebar expands and collapses correctly
- [ ] Keyboard shortcut (Ctrl/Cmd + B) works
- [ ] Mobile drawer opens and closes
- [ ] Navigation items render correctly
- [ ] Tooltips appear when collapsed
- [ ] All sidebar variants work (sidebar, floating, inset)
- [ ] All collapsible modes work (offcanvas, icon, none)

### Component-Specific Tests
- [ ] `SidebarProvider` provides context correctly
- [ ] `useSidebar` hook returns expected values
- [ ] `SidebarTrigger` toggles sidebar state
- [ ] `SidebarRail` toggles sidebar state
- [ ] `SidebarMenuButton` tooltip behavior (shows when collapsed only)
- [ ] `SidebarMenuSkeleton` renders loading state

---

## Risk Assessment

### Low Risk
- Type extraction (no runtime changes)
- Constant extraction (no runtime changes)
- Layout components (simple presentational)

### Medium Risk
- Context/Provider extraction (core functionality)
- Menu components (most complex, has CVA variants)

### Mitigation
- Keep `"use client"` directive in all component files
- Ensure all exports are exactly as before
- Run full test suite before committing
- Test manually in development environment

---

## Estimated Effort

| Task | Time Estimate |
|------|---------------|
| Create directory structure | 5 min |
| Extract types and constants | 15 min |
| Extract SidebarContext | 20 min |
| Extract Sidebar | 15 min |
| Extract SidebarTrigger | 10 min |
| Extract SidebarLayout | 15 min |
| Extract SidebarContent | 5 min |
| Extract SidebarGroup | 15 min |
| Extract SidebarMenu | 25 min |
| Extract SidebarMenuSub | 10 min |
| Create index.ts | 10 min |
| Testing and verification | 30 min |
| Cleanup and commit | 10 min |
| **Total** | **~3 hours** |

---

## Notes

- This is a shadcn/ui component, so it follows their patterns
- The `"use client"` directive is required for React hooks
- The `eslint-disable react-refresh/only-export-components` comment in the original file can be removed since each file will export its own components
- CVA (class-variance-authority) variants should stay with their component in `SidebarMenu.tsx`
