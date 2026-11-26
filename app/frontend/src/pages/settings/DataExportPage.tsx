import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, Loader2, FileArchive, AlertCircle, Clock, CheckCircle, XCircle } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  useRequestExportMutation,
  useGetExportsQuery,
  useGetExportDownloadMutation,
  type DataExportRequest,
} from '@/features/user/userApi'
import { useAppSelector } from '@/store/hooks'
import { toast } from 'sonner'
import { getErrorMessage } from '@/types/api'
import { safeOpenDownloadUrl } from '@/lib/url-validation'

export function DataExportPage() {
  const { t } = useTranslation(['settings', 'backend'])
  const { data: exportsData, isLoading, error } = useGetExportsQuery()
  const [requestExport, { isLoading: isRequesting }] = useRequestExportMutation()
  const [getDownloadUrl] = useGetExportDownloadMutation()
  const [downloadingExportId, setDownloadingExportId] = useState<string | null>(null)
  const token = useAppSelector((state) => state.auth.token)

  const handleRequestExport = async () => {
    try {
      await requestExport().unwrap()
      toast.success(t('settings:dataExport.messages.requestSuccess'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  const handleDownload = async (exportId: string) => {
    setDownloadingExportId(exportId)
    try {
      const response = await getDownloadUrl(exportId).unwrap()
      const downloadUrl = response.download_url

      // Check if this is a backend URL (needs auth) vs S3 signed URL (pre-authenticated)
      // Backend URLs contain '/api/v1/users/me/exports/' while S3 URLs are on different hosts
      if (downloadUrl.includes('/api/v1/users/me/exports/') && downloadUrl.includes('/download-file')) {
        // Local storage - need to fetch with auth and trigger download via blob
        const fetchResponse = await fetch(downloadUrl, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
        if (!fetchResponse.ok) {
          throw new Error('Download failed')
        }
        const blob = await fetchResponse.blob()
        const blobUrl = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = blobUrl
        link.download = `data_export_${exportId}.zip`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(blobUrl)
      } else {
        // S3 signed URL - validate and open directly in new window
        // SEC-F-011: Validate URL origin before opening
        if (!safeOpenDownloadUrl(downloadUrl)) {
          throw new Error('Invalid download URL')
        }
      }
      toast.success(t('settings:dataExport.messages.downloadStarted'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    } finally {
      setDownloadingExportId(null)
    }
  }

  const getStatusBadge = (status: DataExportRequest['status']) => {
    switch (status) {
      case 'pending':
        return (
          <Badge variant="secondary" className="gap-1">
            <Clock className="h-3 w-3" />
            {t('settings:dataExport.status.pending')}
          </Badge>
        )
      case 'processing':
        return (
          <Badge variant="secondary" className="gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t('settings:dataExport.status.processing')}
          </Badge>
        )
      case 'completed':
        return (
          <Badge variant="default" className="gap-1">
            <CheckCircle className="h-3 w-3" />
            {t('settings:dataExport.status.completed')}
          </Badge>
        )
      case 'failed':
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            {t('settings:dataExport.status.failed')}
          </Badge>
        )
      case 'expired':
        return (
          <Badge variant="outline" className="gap-1">
            <AlertCircle className="h-3 w-3" />
            {t('settings:dataExport.status.expired')}
          </Badge>
        )
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  const formatFileSize = (bytes: number | null) => {
    if (!bytes) return t('settings:dataExport.labels.calculating')

    const units = ['B', 'KB', 'MB', 'GB']
    let size = bytes
    let unitIndex = 0

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex++
    }

    return `${size.toFixed(2)} ${units[unitIndex]}`
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('settings:dataExport.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:dataExport.error.description')}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:dataExport.title')}</CardTitle>
          <CardDescription>{t('settings:dataExport.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <Alert>
            <FileArchive className="h-4 w-4" />
            <AlertTitle>{t('settings:dataExport.info.title')}</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{t('settings:dataExport.info.description')}</p>
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>{t('settings:dataExport.info.includes.profile')}</li>
                <li>{t('settings:dataExport.info.includes.organizations')}</li>
                <li>{t('settings:dataExport.info.includes.activity')}</li>
                <li>{t('settings:dataExport.info.includes.files')}</li>
              </ul>
              <p className="text-sm text-muted-foreground mt-2">
                {t('settings:dataExport.info.retention')}
              </p>
            </AlertDescription>
          </Alert>

          <div>
            <Button
              onClick={handleRequestExport}
              disabled={isRequesting}
              className="gap-2"
            >
              {isRequesting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('settings:dataExport.buttons.requesting')}
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  {t('settings:dataExport.buttons.requestExport')}
                </>
              )}
            </Button>
          </div>

          {exportsData && exportsData.items.length > 0 && (
            <>
              <Separator />
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">
                  {t('settings:dataExport.history.title')}
                </h3>
                <div className="space-y-3">
                  {exportsData.items.map((exportRequest) => (
                    <Card key={exportRequest.id} className="bg-muted/50">
                      <CardContent className="pt-6">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 space-y-2">
                            <div className="flex items-center gap-2">
                              {getStatusBadge(exportRequest.status)}
                              <span className="text-sm text-muted-foreground">
                                {t('settings:dataExport.labels.requested')}{' '}
                                {formatDate(exportRequest.created_time)}
                              </span>
                            </div>

                            {exportRequest.status === 'completed' && (
                              <div className="space-y-1 text-sm">
                                <p className="text-muted-foreground">
                                  {t('settings:dataExport.labels.size')}:{' '}
                                  <span className="font-medium text-foreground">
                                    {formatFileSize(exportRequest.file_size_bytes)}
                                  </span>
                                </p>
                                <p className="text-muted-foreground">
                                  {t('settings:dataExport.labels.downloads')}:{' '}
                                  <span className="font-medium text-foreground">
                                    {exportRequest.download_count}
                                  </span>
                                </p>
                                {exportRequest.expires_at && (
                                  <p className="text-muted-foreground">
                                    {t('settings:dataExport.labels.expires')}:{' '}
                                    <span className="font-medium text-foreground">
                                      {formatDate(exportRequest.expires_at)}
                                    </span>
                                  </p>
                                )}
                              </div>
                            )}

                            {exportRequest.status === 'failed' && (
                              <p className="text-sm text-destructive">
                                {t('settings:dataExport.messages.exportFailed')}
                              </p>
                            )}

                            {exportRequest.status === 'expired' && (
                              <p className="text-sm text-muted-foreground">
                                {t('settings:dataExport.messages.exportExpired')}
                              </p>
                            )}

                            {(exportRequest.status === 'pending' ||
                              exportRequest.status === 'processing') && (
                              <p className="text-sm text-muted-foreground">
                                {t('settings:dataExport.messages.processing')}
                              </p>
                            )}
                          </div>

                          {exportRequest.status === 'completed' && (
                            <Button
                              onClick={() => handleDownload(exportRequest.id)}
                              disabled={downloadingExportId === exportRequest.id}
                              size="sm"
                              className="gap-2"
                            >
                              {downloadingExportId === exportRequest.id ? (
                                <>
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                  {t('settings:dataExport.buttons.downloading')}
                                </>
                              ) : (
                                <>
                                  <Download className="h-3 w-3" />
                                  {t('settings:dataExport.buttons.download')}
                                </>
                              )}
                            </Button>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
