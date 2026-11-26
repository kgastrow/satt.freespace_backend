import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader } from '@/components/ui/card'

interface CardSkeletonProps {
  variant?: 'default' | 'stats' | 'grid-item'
  className?: string
}

/**
 * Skeleton loader for card-based content
 *
 * @example
 * <CardSkeleton variant="default" />
 * <CardSkeleton variant="stats" />
 * <CardSkeleton variant="grid-item" />
 */
export function CardSkeleton({
  variant = 'default',
  className,
}: CardSkeletonProps) {
  if (variant === 'stats') {
    return (
      <Card className={className}>
        <CardContent className="p-6">
          <div className="flex items-center gap-4">
            <Skeleton className="h-12 w-12 rounded-lg" />
            <div className="space-y-2 flex-1">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-8 w-16" />
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (variant === 'grid-item') {
    return (
      <Card className={className}>
        <CardContent className="p-4">
          <Skeleton className="h-32 w-full rounded-md mb-3" />
          <Skeleton className="h-4 w-3/4 mb-2" />
          <Skeleton className="h-3 w-1/2" />
        </CardContent>
      </Card>
    )
  }

  // Default variant
  return (
    <Card className={className}>
      <CardHeader>
        <Skeleton className="h-6 w-1/3 mb-2" />
        <Skeleton className="h-4 w-2/3" />
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </div>
      </CardContent>
    </Card>
  )
}
