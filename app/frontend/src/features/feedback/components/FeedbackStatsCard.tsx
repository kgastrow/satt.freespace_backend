import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Feedback } from '../types'
import { MessageSquare, Star, CheckCircle } from 'lucide-react'

interface FeedbackStatsCardProps {
  feedbacks: Feedback[]
}

export function FeedbackStatsCard({ feedbacks }: FeedbackStatsCardProps) {
  const { t } = useTranslation('feedback')

  const bugCount = feedbacks.filter((f) => f.type === 'bug').length
  const suggestionCount = feedbacks.filter((f) => f.type === 'suggestion').length
  const complaintCount = feedbacks.filter((f) => f.type === 'complaint').length
  const praiseCount = feedbacks.filter((f) => f.type === 'praise').length
  const otherCount = feedbacks.filter((f) => f.type === 'other').length

  const ratingsWithValues = feedbacks.filter((f) => f.rating !== null)
  const averageRating =
    ratingsWithValues.length > 0
      ? ratingsWithValues.reduce((sum, f) => sum + (f.rating || 0), 0) / ratingsWithValues.length
      : 0

  const resolvedCount = feedbacks.filter((f) => f.status === 'resolved').length

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{t('admin.stats.byType')}</CardTitle>
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('form.fields.type.options.bug')}</span>
              <span className="font-medium">{bugCount}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('form.fields.type.options.suggestion')}</span>
              <span className="font-medium">{suggestionCount}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('form.fields.type.options.complaint')}</span>
              <span className="font-medium">{complaintCount}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('form.fields.type.options.praise')}</span>
              <span className="font-medium">{praiseCount}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('form.fields.type.options.other')}</span>
              <span className="font-medium">{otherCount}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{t('admin.stats.averageRating')}</CardTitle>
          <Star className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {averageRating > 0 ? averageRating.toFixed(1) : '—'}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {t('admin.stats.outOf5', { count: ratingsWithValues.length })}
          </p>
          {averageRating > 0 && (
            <div className="flex items-center gap-1 mt-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <span
                  key={i}
                  className={i < Math.round(averageRating) ? 'text-yellow-500' : 'text-gray-300'}
                >
                  ★
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{t('admin.stats.resolved')}</CardTitle>
          <CheckCircle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{resolvedCount}</div>
          <p className="text-xs text-muted-foreground mt-1">
            {t('admin.stats.ofTotal', { total: feedbacks.length })}
          </p>
          {feedbacks.length > 0 && (
            <div className="mt-2">
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary"
                  style={{ width: `${(resolvedCount / feedbacks.length) * 100}%` }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  )
}
