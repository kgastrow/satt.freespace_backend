import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Copy, Download, Check, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface BackupCodesDisplayProps {
  backupCodes: string[]
  onComplete: () => void
}

export function BackupCodesDisplay({ backupCodes, onComplete }: BackupCodesDisplayProps) {
  const { t } = useTranslation(['settings'])
  const [copiedAll, setCopiedAll] = useState(false)

  const handleCopyAll = async () => {
    const codesText = backupCodes.join('\n')
    await navigator.clipboard.writeText(codesText)
    setCopiedAll(true)
    toast.success(t('settings:twoFactor.backupCodes.messages.copied'))
    setTimeout(() => setCopiedAll(false), 2000)
  }

  const handleDownload = () => {
    const codesText = backupCodes.join('\n')
    const blob = new Blob([codesText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `2fa-backup-codes-${new Date().toISOString().split('T')[0]}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success(t('settings:twoFactor.backupCodes.messages.downloaded'))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings:twoFactor.backupCodes.title')}</CardTitle>
        <CardDescription>{t('settings:twoFactor.backupCodes.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('settings:twoFactor.backupCodes.warning.title')}</AlertTitle>
          <AlertDescription>{t('settings:twoFactor.backupCodes.warning.description')}</AlertDescription>
        </Alert>

        <div className="grid grid-cols-2 gap-3">
          {backupCodes.map((code, index) => (
            <div
              key={index}
              className="px-4 py-3 bg-muted rounded-md text-center font-mono text-sm"
            >
              {code}
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" onClick={handleCopyAll} className="flex-1">
            {copiedAll ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
            {t('settings:twoFactor.backupCodes.buttons.copy')}
          </Button>
          <Button variant="outline" onClick={handleDownload} className="flex-1">
            <Download className="mr-2 h-4 w-4" />
            {t('settings:twoFactor.backupCodes.buttons.download')}
          </Button>
        </div>

        <Button onClick={onComplete} className="w-full">
          {t('settings:twoFactor.backupCodes.buttons.complete')}
        </Button>
      </CardContent>
    </Card>
  )
}
