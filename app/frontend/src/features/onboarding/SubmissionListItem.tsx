import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { User, Clock, AlertCircle } from 'lucide-react'
import type { PendingReviewSubmission } from '@/store/api/onboardingApi'

interface SubmissionListItemProps {
  submission: PendingReviewSubmission
  isSelected: boolean
  onClick: () => void
}

export function SubmissionListItem({
  submission,
  isSelected,
  onClick,
}: SubmissionListItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left p-4 border-b transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
        isSelected
          ? 'bg-accent border-l-2 border-l-primary'
          : 'hover:bg-muted/50 border-l-2 border-l-transparent'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="font-medium truncate">
              {submission.user_first_name} {submission.user_last_name}
            </span>
            {submission.requires_admin_attention && (
              <span className="flex-shrink-0" title="Action required">
                <AlertCircle className="h-4 w-4 text-destructive" />
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground truncate mt-1">
            {submission.user_email}
          </p>
        </div>
        <Badge variant="secondary" className="flex-shrink-0">
          {submission.user_type_name}
        </Badge>
      </div>
      <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
        <Clock className="h-3 w-3" />
        <time dateTime={submission.submitted_at}>
          {new Date(submission.submitted_at).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </time>
      </div>
    </button>
  )
}
