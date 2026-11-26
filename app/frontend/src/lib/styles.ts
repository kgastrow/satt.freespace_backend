import { cn } from './utils'

// Layout presets
export const layout = {
  flexCenter: 'flex items-center justify-center',
  flexBetween: 'flex items-center justify-between',
  flexStart: 'flex items-center justify-start',
  flexCol: 'flex flex-col',
  flexColCenter: 'flex flex-col items-center justify-center',
  stack: (gap: number = 4) => `flex flex-col gap-${gap}`,
  row: (gap: number = 4) => `flex items-center gap-${gap}`,
  grid: (cols: number = 2) => `grid grid-cols-${cols} gap-4`,
  gridResponsive: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4',
} as const

// Container presets
export const container = {
  page: 'container mx-auto px-4 py-6',
  section: 'space-y-6',
  card: 'rounded-lg border bg-card p-6 shadow-sm',
  cardCompact: 'rounded-lg border bg-card p-4 shadow-sm',
  panel: 'rounded-lg bg-muted/50 p-4',
} as const

// Typography presets
export const text = {
  h1: 'text-4xl font-bold tracking-tight',
  h2: 'text-3xl font-semibold tracking-tight',
  h3: 'text-2xl font-semibold tracking-tight',
  h4: 'text-xl font-semibold',
  body: 'text-base text-foreground',
  small: 'text-sm text-foreground',
  muted: 'text-sm text-muted-foreground',
  label: 'text-sm font-medium',
  error: 'text-sm text-destructive',
  success: 'text-sm text-success',
} as const

// Interactive presets
export const interactive = {
  clickable: 'cursor-pointer transition-colors hover:bg-accent',
  focusRing: 'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  disabled: 'disabled:pointer-events-none disabled:opacity-50',
} as const

// Animation presets
export const animation = {
  fadeIn: 'animate-in fade-in duration-200',
  fadeOut: 'animate-out fade-out duration-200',
  slideIn: 'animate-in slide-in-from-bottom-4 duration-200',
  spin: 'animate-spin',
} as const

// Combine utility (re-export cn with an alias for consistency)
export function styles(...classes: (string | undefined | false)[]) {
  return cn(...classes)
}
