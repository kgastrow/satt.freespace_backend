import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useGetOnboardingStatusQuery } from '@/store/api/onboardingApi'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { X, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import { WithdrawAction } from './WithdrawAction'

const DISMISSAL_STORAGE_KEY = 'onboarding_status_dismissed'
const FOURTEEN_DAYS_MS = 14 * 24 * 60 * 60 * 1000

interface DismissalData {
  status: string
  dismissedAt: number
}

function getDismissalData(): DismissalData | null {
  try {
    const stored = localStorage.getItem(DISMISSAL_STORAGE_KEY)
    return stored ? JSON.parse(stored) : null
  } catch {
    return null
  }
}

function setDismissalData(status: string): void {
  try {
    const data: DismissalData = { status, dismissedAt: Date.now() }
    localStorage.setItem(DISMISSAL_STORAGE_KEY, JSON.stringify(data))
  } catch {
    // Ignore localStorage errors
  }
}

function clearDismissalData(): void {
  try {
    localStorage.removeItem(DISMISSAL_STORAGE_KEY)
  } catch {
    // Ignore localStorage errors
  }
}

export function OnboardingProgressCard() {
  const { t } = useTranslation('onboarding')
  const isOnboardingEnabled = useFeatureFlag('user_onboarding')
  const { data: status, isLoading } = useGetOnboardingStatusQuery(undefined, {
    skip: !isOnboardingEnabled,
  })
  // Initialize dismissed state from localStorage (lazy initializer runs once)
  const [isDismissed, setIsDismissed] = useState(() => {
    const dismissalData = getDismissalData()
    if (!dismissalData) return false

    // Check if 14 days have passed since dismissal
    const timeSinceDismissal = Date.now() - dismissalData.dismissedAt
    if (timeSinceDismissal > FOURTEEN_DAYS_MS) {
      clearDismissalData()
      return false
    }

    return true
  })

  // Check if dismissal should be cleared when status changes
  const dismissalData = getDismissalData()
  if (isDismissed && status && dismissalData && dismissalData.status !== status.status) {
    clearDismissalData()
    setIsDismissed(false)
  }

  const handleDismiss = useCallback(() => {
    if (status) {
      setDismissalData(status.status)
      setIsDismissed(true)
    }
  }, [status])

  // Don't show if feature flag is disabled
  if (!isOnboardingEnabled) {
    return null
  }

  if (isLoading || !status) {
    return null
  }

  // Show approved/rejected status card (dismissible, 14 days)
  if (status.status === 'approved' || status.status === 'rejected') {
    if (isDismissed) {
      return null
    }

    const isApproved = status.status === 'approved'

    return (
      <Card className={isApproved ? 'border-success/50 bg-success/5' : 'border-destructive/50 bg-destructive/5'}>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              {isApproved ? (
                <CheckCircle2 className="h-5 w-5 text-success" />
              ) : (
                <XCircle className="h-5 w-5 text-destructive" />
              )}
              <CardTitle className="text-base">
                {isApproved
                  ? t('progressCard.approvedTitle')
                  : t('progressCard.rejectedTitle')}
              </CardTitle>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 -mr-2 -mt-1"
              onClick={handleDismiss}
              aria-label={t('progressCard.dismiss')}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <CardDescription>
            {isApproved
              ? t('progressCard.approvedDescription')
              : t('progressCard.rejectedDescription')}
          </CardDescription>
        </CardHeader>
        {!isApproved && (
          <CardContent className="pt-0">
            <Button asChild variant="outline" size="sm">
              <Link to="/onboarding">{t('progressCard.reviewSubmission')}</Link>
            </Button>
          </CardContent>
        )}
      </Card>
    )
  }

  // Show change requested status card (not dismissible - action required)
  if (status.status === 'change_requested') {
    return (
      <Card className="border-amber-500/50 bg-amber-50/50 dark:bg-amber-950/20">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-amber-600" />
            <CardTitle className="text-base">
              {t('progressCard.changeRequestedTitle')}
            </CardTitle>
          </div>
          <CardDescription>
            {t('progressCard.changeRequestedDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild size="sm">
              <Link to="/onboarding">{t('progressCard.editSubmission')}</Link>
            </Button>
            {status.user_user_type_id && (
              <WithdrawAction
                userUserTypeId={status.user_user_type_id}
                status="change_requested"
                userTypeName={status.user_type?.name || ''}
              />
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  // For "not_started" status, show a get started card
  const isNotStarted = status.status === 'not_started'

  // For in_progress/pending_review, check if there are steps and user type
  if (!isNotStarted) {
    const hasOnboardingSteps = status.total_steps_count > 0
    const hasUserType = status.user_type !== null
    if (!hasOnboardingSteps || !hasUserType) {
      return null
    }
  }

  // Show "Get Started" card for not_started status
  if (isNotStarted) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('progressCard.getStartedTitle')}</CardTitle>
          <CardDescription>{t('progressCard.getStartedDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link to="/onboarding">{t('progressCard.getStartedButton')}</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  const progressPercentage =
    status.total_steps_count > 0
      ? (status.completed_steps_count / status.total_steps_count) * 100
      : 0

  const isPendingReview = status.status === 'pending_review'

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{t('progressCard.title')}</CardTitle>
          {isPendingReview && (
            <Badge variant="secondary">{t('progressCard.pendingReviewBadge')}</Badge>
          )}
        </div>
        <CardDescription>
          {isPendingReview
            ? t('progressCard.pendingReviewDescription', { userType: status.user_type?.name })
            : t('progressCard.description', { userType: status.user_type?.name })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {t('progressCard.progressLabel', {
                completed: status.completed_steps_count,
                total: status.total_steps_count,
              })}
            </span>
            <span className="font-medium">{Math.round(progressPercentage)}%</span>
          </div>
          <Progress value={progressPercentage} />
        </div>

        {status.current_step && !isPendingReview && (
          <div className="rounded-lg border bg-muted/50 p-3">
            <p className="text-sm font-medium">{t('progressCard.currentStep')}</p>
            <p className="text-sm text-muted-foreground">{status.current_step.name}</p>
          </div>
        )}

        {!isPendingReview && (
          <Button asChild className="w-full">
            <Link to="/onboarding">{t('progressCard.continueButton')}</Link>
          </Button>
        )}

        {status.user_user_type_id && (isPendingReview || status.status === 'in_progress') && (
          <div className="flex justify-center">
            <WithdrawAction
              userUserTypeId={status.user_user_type_id}
              status={isPendingReview ? 'pending_review' : 'in_progress'}
              userTypeName={status.user_type?.name || ''}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
