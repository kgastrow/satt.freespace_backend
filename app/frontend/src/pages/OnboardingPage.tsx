import { useTranslation } from 'react-i18next'
import { OnboardingWizard } from '@/features/onboarding/OnboardingWizard'
import { useGetOnboardingStatusQuery } from '@/store/api/onboardingApi'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'

export function OnboardingPage() {
  const { t } = useTranslation('onboarding')
  const isOnboardingEnabled = useFeatureFlag('user_onboarding')
  const { data: status } = useGetOnboardingStatusQuery(undefined, {
    skip: !isOnboardingEnabled,
  })

  const userTypeName = status?.user_type?.name
  const isPendingOrComplete = status?.status === 'pending_review' || status?.status === 'approved' || status?.status === 'rejected'

  return (
    <div className="container max-w-4xl mx-auto py-8 px-4">
      {/* Only show header when actively completing onboarding */}
      {!isPendingOrComplete && (
        <div className="space-y-2 mb-8">
          <h1 className="text-3xl font-bold tracking-tight">{t('page.title')}</h1>
          <p className="text-muted-foreground">
            {userTypeName
              ? t('page.descriptionWithUserType', { userType: userTypeName })
              : t('page.description')}
          </p>
        </div>
      )}

      <OnboardingWizard />
    </div>
  )
}
