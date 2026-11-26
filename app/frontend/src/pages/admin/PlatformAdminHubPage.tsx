import { useTranslation } from 'react-i18next'

export function PlatformAdminHubPage() {
  const { t } = useTranslation('platformAdmin')

  return (
    <div className="text-center py-12">
      <p className="text-muted-foreground">
        {t('selectFromSidebar', 'Select an option from the sidebar to get started.')}
      </p>
    </div>
  )
}
