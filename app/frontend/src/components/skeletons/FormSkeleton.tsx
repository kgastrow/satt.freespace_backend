import { Skeleton } from '@/components/ui/skeleton'

interface FormSkeletonProps {
  fields?: number
  className?: string
}

/**
 * Skeleton loader for form content
 *
 * @example
 * <FormSkeleton fields={4} />
 */
export function FormSkeleton({ fields = 4, className }: FormSkeletonProps) {
  return (
    <div className={className}>
      <div className="space-y-6">
        {Array.from({ length: fields }).map((_, index) => (
          <div key={index} className="space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-10 w-full rounded-md" />
          </div>
        ))}
        <div className="pt-4">
          <Skeleton className="h-10 w-32 rounded-md" />
        </div>
      </div>
    </div>
  )
}
