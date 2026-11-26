import { cn } from '@/lib/utils'

interface SpinnerProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-8 w-8',
}

/**
 * Loading spinner component
 *
 * @deprecated For page/section loading states, use skeleton loaders from @/components/skeletons instead.
 * This component should only be used for inline loading indicators (e.g., button loading states).
 *
 * @example
 * // For inline loading (OK to use)
 * <Button disabled={isLoading}>
 *   {isLoading && <Spinner size="sm" />}
 *   Submit
 * </Button>
 *
 * // For page loading (use skeleton loaders instead)
 * // ❌ Don't: <Spinner />
 * // ✅ Do: <TableSkeleton columns={columns} />
 */
export function Spinner({ className, size = 'md' }: SpinnerProps) {
  return (
    <svg
      className={cn('animate-spin', sizeClasses[size], className)}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-label="Loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}
