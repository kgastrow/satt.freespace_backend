import { useTranslation } from 'react-i18next'
import { Construction } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface ComingSoonPlaceholderProps {
  titleKey: string
  descriptionKey?: string
}

export function ComingSoonPlaceholder({ titleKey, descriptionKey }: ComingSoonPlaceholderProps) {
  const { t } = useTranslation('settings')

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>{t(titleKey)}</CardTitle>
        {descriptionKey && <CardDescription>{t(descriptionKey)}</CardDescription>}
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Construction className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">{t('placeholder.comingSoon')}</h3>
          <p className="text-sm text-muted-foreground max-w-md">
            {t('placeholder.description')}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
