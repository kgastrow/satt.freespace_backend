import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { OnboardingStep } from './OnboardingStep'
import { PhoneVerificationStep } from './PhoneVerificationStep'
import {
  useGetOnboardingStatusQuery,
  useGetActiveUserTypesQuery,
  useStartOnboardingMutation,
  useGetMyReviewCommentsQuery,
  useRespondToChangeRequestMutation,
  useResubmitForReviewMutation,
} from '@/store/api/onboardingApi'
import { WithdrawAction } from './WithdrawAction'
import { useGetCurrentUserQuery } from '@/features/auth/authApi'
import { Skeleton } from '@/components/ui/skeleton'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { AlertCircle, MessageSquare, User, Shield, Loader2 } from 'lucide-react'

interface UserTypeSelectionProps {
  assignedTypeIds?: Set<string>
}

function UserTypeSelection({ assignedTypeIds = new Set() }: UserTypeSelectionProps) {
  const { t } = useTranslation('onboarding')
  const {
    data: userTypes,
    isLoading: isLoadingTypes,
    isError: isTypesError,
  } = useGetActiveUserTypesQuery()
  const [startOnboarding, { isLoading: isStarting }] = useStartOnboardingMutation()
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null)

  // Filter out already-assigned user types and sort by display order
  const availableUserTypes = useMemo(() => {
    if (!userTypes) return []
    return [...userTypes]
      .filter((ut) => !assignedTypeIds.has(ut.id))
      .sort((a, b) => a.display_order - b.display_order)
  }, [userTypes, assignedTypeIds])

  const handleSelectUserType = async (userTypeId: string) => {
    setSelectedTypeId(userTypeId)
    try {
      await startOnboarding(userTypeId).unwrap()
      // RTK Query will auto-refetch the status, triggering the wizard to show the first step
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('errors.startFailed'))
      setSelectedTypeId(null)
    }
  }

  if (isLoadingTypes) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-72 mt-2" />
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (isTypesError || !userTypes || availableUserTypes.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.userTypeSelection.title')}</CardTitle>
          <CardDescription>{t('wizard.userTypeSelection.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">{t('wizard.userTypeSelection.noUserTypes')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('wizard.userTypeSelection.title')}</CardTitle>
        <CardDescription>{t('wizard.userTypeSelection.description')}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {availableUserTypes.map((userType) => (
            <Card
              key={userType.id}
              className="relative overflow-hidden transition-colors hover:border-primary/50"
            >
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">{userType.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {userType.description && (
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {userType.description}
                  </p>
                )}
                <Button
                  onClick={() => handleSelectUserType(userType.id)}
                  disabled={isStarting}
                  className="w-full"
                >
                  {isStarting && selectedTypeId === userType.id
                    ? t('wizard.userTypeSelection.selecting')
                    : t('wizard.userTypeSelection.select')}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function OnboardingWizard() {
  const { t } = useTranslation('onboarding')
  const navigate = useNavigate()
  const isOnboardingEnabled = useFeatureFlag('user_onboarding')
  const { data: status, isLoading, refetch } = useGetOnboardingStatusQuery(undefined, {
    skip: !isOnboardingEnabled,
  })
  const { data: currentUser } = useGetCurrentUserQuery()
  const [manualStepIndex, setManualStepIndex] = useState<number | null>(null)
  const [responseComment, setResponseComment] = useState('')
  const [isEditingSteps, setIsEditingSteps] = useState(false)

  // Comments and action hooks for change_requested status
  const isChangeRequested = status?.status === 'change_requested'
  const userUserTypeId = status?.user_user_type_id
  const { data: commentsData } = useGetMyReviewCommentsQuery(userUserTypeId || '', {
    skip: !isChangeRequested || !userUserTypeId,
  })
  const [respondToChangeRequest, { isLoading: isResponding }] = useRespondToChangeRequestMutation()
  const [resubmitForReview, { isLoading: isResubmitting }] = useResubmitForReviewMutation()

  // Build completedStepIds early so it can be used for currentStepIndex calculation
  const completedStepIds = useMemo(() => {
    if (!status?.progress) return new Set<string>()
    return new Set(status.progress.map((p) => p.onboarding_step_id))
  }, [status])

  const currentStepIndex = useMemo(() => {
    if (manualStepIndex !== null) return manualStepIndex
    if (!status) return 0

    // Find the first step that is NOT completed
    // This handles reusable steps (like phone verification) that may be pre-completed
    // from a previous onboarding while earlier steps remain incomplete
    const firstIncompleteIndex = status.steps.findIndex((step) => !completedStepIds.has(step.id))

    // If all steps completed, stay on last step
    return firstIncompleteIndex >= 0 ? firstIncompleteIndex : status.steps.length - 1
  }, [manualStepIndex, status, completedStepIds])

  // Compute these values before any early returns to satisfy React hooks rules
  const currentStep = status?.steps?.[currentStepIndex]
  const submittedData = status?.progress?.find((p) => p.onboarding_step_id === currentStep?.id)?.submitted_data

  // Merge user profile data with any previously submitted data
  // This pre-fills fields like first_name, last_name from registration
  const initialData = useMemo(() => {
    const userData: Record<string, unknown> = {}
    if (currentUser) {
      // Support common field naming conventions
      if (currentUser.first_name) {
        userData.first_name = currentUser.first_name
        userData.firstName = currentUser.first_name
      }
      if (currentUser.last_name) {
        userData.last_name = currentUser.last_name
        userData.lastName = currentUser.last_name
      }
      if (currentUser.email) {
        userData.email = currentUser.email
      }
      if (currentUser.phone) {
        userData.phone = currentUser.phone
      }
    }
    // Previously submitted data takes precedence
    return { ...userData, ...submittedData }
  }, [currentUser, submittedData])

  useEffect(() => {
    // Only auto-redirect to dashboard if approved AND no more types can be added
    if (status?.status === 'approved' && !status?.can_add_more_types) {
      toast.success(t('wizard.approved'))
      navigate('/dashboard')
    }
  }, [status?.status, status?.can_add_more_types, navigate, t])

  const handleStepComplete = async () => {
    setManualStepIndex(null)
    await refetch()
  }

  const handleBack = () => {
    if (currentStepIndex > 0) {
      setManualStepIndex(currentStepIndex - 1)
    }
  }

  const handleStepClick = (index: number) => {
    // Only allow clicking on completed steps or current step
    const step = status?.steps[index]
    if (!step) return

    const isCompleted = completedStepIds.has(step.id)
    const isCurrent = index === currentStepIndex

    if (isCompleted || isCurrent) {
      setManualStepIndex(index)
    }
  }

  const handleRespondToChange = async () => {
    if (!responseComment.trim() || !userUserTypeId) return

    try {
      await respondToChangeRequest({
        user_user_type_id: userUserTypeId,
        comment: responseComment,
      }).unwrap()
      toast.success(t('wizard.changeRequested.respondSuccess'))
      setResponseComment('')
      await refetch()
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('wizard.changeRequested.respondError'))
    }
  }

  const handleResubmit = async () => {
    if (!userUserTypeId) return

    try {
      await resubmitForReview(userUserTypeId).unwrap()
      toast.success(t('wizard.changeRequested.resubmitSuccess'))
      setIsEditingSteps(false)
      await refetch()
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('wizard.changeRequested.resubmitError'))
    }
  }

  // Get assigned user type IDs to filter in UserTypeSelection
  // Must be computed before early returns to satisfy React hooks rules
  const assignedTypeIds = useMemo(() => {
    return new Set(status?.all_user_types?.map((ut) => ut.user_type_id) || [])
  }, [status?.all_user_types])

  // Redirect to dashboard if onboarding is disabled
  useEffect(() => {
    if (!isOnboardingEnabled) {
      navigate('/dashboard')
    }
  }, [isOnboardingEnabled, navigate])

  if (!isOnboardingEnabled) {
    return null
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
          <p className="text-muted-foreground">{t('wizard.loading')}</p>
        </div>
      </div>
    )
  }

  // Show UserTypeSelection if:
  // 1. User hasn't started onboarding at all
  // 2. User has completed/rejected onboarding but can add more types
  const shouldShowUserTypeSelection =
    !status ||
    status.status === 'not_started' ||
    (status.can_add_more_types && (status.status === 'approved' || status.status === 'rejected'))

  if (shouldShowUserTypeSelection) {
    return <UserTypeSelection assignedTypeIds={assignedTypeIds} />
  }

  if (status.status === 'pending_review') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.pendingReview.title')}</CardTitle>
          <CardDescription>
            {status.user_type?.name
              ? t('wizard.userTypeContext', { userType: status.user_type.name }) +
                ' · ' +
                t('wizard.pendingReview.description')
              : t('wizard.pendingReview.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{t('wizard.pendingReview.badge')}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t('wizard.pendingReview.info')}</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => navigate('/dashboard')}>{t('wizard.pendingReview.goToDashboard')}</Button>
            {status.user_user_type_id && (
              <WithdrawAction
                userUserTypeId={status.user_user_type_id}
                status="pending_review"
                userTypeName={status.user_type?.name || ''}
              />
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  // Show change requested status - user can respond, edit steps, and resubmit
  if (status.status === 'change_requested' && !isEditingSteps) {
    const latestAdminComment = commentsData?.comments?.find((c) => c.author_type === 'admin')

    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{t('wizard.changeRequested.title')}</CardTitle>
              <Badge variant="outline" className="gap-1 border-amber-500 bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400">
                <AlertCircle className="h-3 w-3" />
                {t('wizard.changeRequested.badge')}
              </Badge>
            </div>
            <CardDescription>
              {status.user_type?.name
                ? t('wizard.userTypeContext', { userType: status.user_type.name }) +
                  ' · ' +
                  t('wizard.changeRequested.description')
                : t('wizard.changeRequested.description')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Alert with latest admin comment */}
            {latestAdminComment && (
              <Alert className="border-amber-500 bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>{t('wizard.changeRequested.latestComment')}</AlertTitle>
                <AlertDescription className="mt-2 whitespace-pre-wrap">
                  {latestAdminComment.comment}
                </AlertDescription>
              </Alert>
            )}

            <p className="text-sm text-muted-foreground">{t('wizard.changeRequested.info')}</p>

            {/* Action buttons */}
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={() => setIsEditingSteps(true)}>
                {t('wizard.changeRequested.editSteps')}
              </Button>
              <Button onClick={handleResubmit} disabled={isResubmitting}>
                {isResubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {t('wizard.changeRequested.resubmit')}
              </Button>
              {userUserTypeId && (
                <WithdrawAction
                  userUserTypeId={userUserTypeId}
                  status="change_requested"
                  userTypeName={status.user_type?.name || ''}
                />
              )}
            </div>

            {/* Comments thread */}
            {commentsData && commentsData.comments.length > 0 && (
              <>
                <Separator />
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                    <h4 className="font-medium text-sm">
                      {t('wizard.changeRequested.commentsTitle')}
                    </h4>
                  </div>
                  <div className="space-y-3 max-h-[300px] overflow-y-auto">
                    {commentsData.comments.map((comment) => (
                      <div
                        key={comment.id}
                        className={`p-3 rounded-lg text-sm ${
                          comment.author_type === 'admin'
                            ? 'bg-muted/50 border-l-2 border-l-primary'
                            : 'bg-info/10 border-l-2 border-l-info'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          {comment.author_type === 'admin' ? (
                            <Shield className="h-3 w-3 text-muted-foreground" />
                          ) : (
                            <User className="h-3 w-3 text-muted-foreground" />
                          )}
                          <span className="font-medium text-xs">
                            {comment.author_name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(comment.created_time).toLocaleString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap">{comment.comment}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Respond with comment */}
            <div className="space-y-3">
              <h4 className="font-medium text-sm">{t('wizard.changeRequested.respondTitle')}</h4>
              <Textarea
                value={responseComment}
                onChange={(e) => setResponseComment(e.target.value)}
                placeholder={t('wizard.changeRequested.respondPlaceholder')}
                rows={3}
                className="text-sm"
              />
              <Button
                onClick={handleRespondToChange}
                disabled={isResponding || !responseComment.trim()}
                variant="secondary"
              >
                {isResponding && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {t('wizard.changeRequested.respond')}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Show rejected status only if user can't add more types
  if (status.status === 'rejected') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.rejected.title')}</CardTitle>
          <CardDescription>{t('wizard.rejected.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant="destructive">{t('wizard.rejected.badge')}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t('wizard.rejected.info')}</p>
        </CardContent>
      </Card>
    )
  }

  // Show approved status only if user can't add more types
  if (status.status === 'approved') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.approved')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Button onClick={() => navigate('/dashboard')}>{t('wizard.pendingReview.goToDashboard')}</Button>
        </CardContent>
      </Card>
    )
  }

  const progress = (status.completed_steps_count / status.total_steps_count) * 100

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <CardTitle>{t('wizard.title')}</CardTitle>
                {status.user_type?.name && (
                  <CardDescription>
                    {t('wizard.userTypeContext', { userType: status.user_type.name })}
                  </CardDescription>
                )}
              </div>
              <Badge variant="secondary">
                {t('wizard.stepProgress', {
                  current: status.completed_steps_count + 1,
                  total: status.total_steps_count,
                })}
              </Badge>
            </div>
            <div className="space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-sm text-muted-foreground">
                {t('wizard.progressDescription', {
                  completed: status.completed_steps_count,
                  total: status.total_steps_count,
                })}
              </p>
            </div>
            {status.user_user_type_id && (
              <div className="flex justify-end">
                <WithdrawAction
                  userUserTypeId={status.user_user_type_id}
                  status="in_progress"
                  userTypeName={status.user_type?.name || ''}
                />
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {currentStep ? (
            currentStep.requires_verification ? (
              <PhoneVerificationStep
                onComplete={handleStepComplete}
                onBack={currentStepIndex > 0 ? handleBack : undefined}
              />
            ) : (
              <OnboardingStep
                step={currentStep}
                onComplete={handleStepComplete}
                onBack={currentStepIndex > 0 ? handleBack : undefined}
                initialData={initialData}
                isLastStep={currentStepIndex === status.steps.length - 1}
              />
            )
          ) : (
            <div className="text-center space-y-4">
              <p className="text-muted-foreground">{t('wizard.noSteps')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {status.steps.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('wizard.allSteps.title')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {status.steps.map((step, index) => {
                const isCompleted = completedStepIds.has(step.id)
                const isCurrent = index === currentStepIndex
                const isClickable = isCompleted || isCurrent

                return (
                <div
                  key={step.id}
                  onClick={() => isClickable && handleStepClick(index)}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                    isCurrent
                      ? 'bg-accent border-primary cursor-pointer'
                      : isCompleted
                        ? 'bg-muted cursor-pointer hover:border-primary/50'
                        : 'opacity-60'
                  }`}
                >
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                      isCompleted
                        ? 'bg-primary text-primary-foreground'
                        : isCurrent
                          ? 'bg-primary/20 text-primary'
                          : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {isCompleted ? '✓' : index + 1}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{step.name}</p>
                    {step.description && (
                      <p className="text-sm text-muted-foreground">{step.description}</p>
                    )}
                  </div>
                  {isCurrent && (
                    <Badge variant="default">{t('wizard.allSteps.current')}</Badge>
                  )}
                  {isCompleted && (
                    <Badge variant="secondary">{t('wizard.allSteps.completed')}</Badge>
                  )}
                </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
