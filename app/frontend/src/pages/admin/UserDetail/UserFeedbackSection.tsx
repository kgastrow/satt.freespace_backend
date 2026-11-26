import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  MessageSquare,
  Clock,
  ArrowRight,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type {
  UserFullDetail,
  FeedbackSummaryInfo,
} from '@/features/users/usersApi'

interface UserFeedbackSectionProps {
  user: UserFullDetail
}

function FeedbackCard({ feedback }: { feedback: FeedbackSummaryInfo }) {
  const navigate = useNavigate()
  const { t } = useTranslation('admin')

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'resolved':
        return <CheckCircle className="h-4 w-4 text-green-600" />
      case 'dismissed':
        return <XCircle className="h-4 w-4 text-destructive" />
      default:
        return <Clock className="h-4 w-4 text-amber-600" />
    }
  }

  const getTypeBadgeVariant = (type: string) => {
    switch (type) {
      case 'bug':
        return 'destructive' as const
      case 'suggestion':
        return 'default' as const
      case 'complaint':
        return 'secondary' as const
      default:
        return 'outline' as const
    }
  }

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'resolved':
        return 'default' as const
      case 'dismissed':
        return 'secondary' as const
      default:
        return 'outline' as const
    }
  }

  return (
    <div
      className="p-4 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={() => navigate(`/admin/feedback/${feedback.id}`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{feedback.subject}</p>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <Badge variant={getTypeBadgeVariant(feedback.type)} className="text-xs">
              {t(`users.detail.feedbackTypes.${feedback.type}`)}
            </Badge>
            <Badge variant={getStatusBadgeVariant(feedback.status)} className="text-xs">
              {getStatusIcon(feedback.status)}
              <span className="ml-1">{t(`users.detail.feedbackStatus.${feedback.status}`)}</span>
            </Badge>
            <span className="text-xs text-muted-foreground">
              {formatDistanceToNow(new Date(feedback.created_time), { addSuffix: true })}
            </span>
          </div>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
      </div>
    </div>
  )
}

export function UserFeedbackSection({ user }: UserFeedbackSectionProps) {
  const { t } = useTranslation('admin')

  if (user.feedback.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium">{t('users.detail.noFeedback')}</h3>
          <p className="text-muted-foreground">{t('users.detail.noFeedbackDescription')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <MessageSquare className="h-5 w-5" />
          {t('users.detail.sections.feedback')}
          <Badge variant="secondary" className="ml-auto">
            {user.feedback.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {user.feedback.map((fb) => (
            <FeedbackCard key={fb.id} feedback={fb} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
