import { useTranslation } from 'react-i18next'
import { HardDrive, Image, Video, FileText, Music, File } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatBytes } from '@/lib/utils'
import type { UserFullDetail } from '@/features/users/usersApi'

interface UserFilesSectionProps {
  user: UserFullDetail
}

interface CategoryCardProps {
  icon: React.ElementType
  label: string
  count: number
  sizeBytes: number
  color: string
}

function CategoryCard({ icon: Icon, label, count, sizeBytes, color }: CategoryCardProps) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">
          {count.toLocaleString()} files
        </p>
      </div>
      <p className="text-sm font-medium">{formatBytes(sizeBytes)}</p>
    </div>
  )
}

export function UserFilesSection({ user }: UserFilesSectionProps) {
  const { t } = useTranslation('admin')

  if (!user.file_usage) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <HardDrive className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium">{t('users.detail.noFiles')}</h3>
          <p className="text-muted-foreground">{t('users.detail.noFilesDescription')}</p>
        </CardContent>
      </Card>
    )
  }

  const { file_usage } = user
  const totalUsed = file_usage.total_size_bytes
  // Assuming a default quota if not specified - in real app this would come from org settings
  const quotaBytes = 5 * 1024 * 1024 * 1024 // 5GB default
  const usagePercent = Math.min((totalUsed / quotaBytes) * 100, 100)

  return (
    <div className="space-y-6">
      {/* Storage Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            {t('users.detail.sections.storageOverview')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                {formatBytes(totalUsed)} {t('users.detail.storage.used')}
              </span>
              <span className="text-sm text-muted-foreground">
                {formatBytes(quotaBytes)} {t('users.detail.storage.total')}
              </span>
            </div>
            <Progress value={usagePercent} className="h-3" />
            <p className="text-xs text-muted-foreground mt-1">
              {usagePercent.toFixed(1)}% {t('users.detail.storage.used')}
            </p>
          </div>

          <div className="flex items-center justify-between pt-2 border-t">
            <span className="text-sm">{t('users.detail.storage.totalFiles')}</span>
            <span className="font-medium">{file_usage.total_files.toLocaleString()}</span>
          </div>
        </CardContent>
      </Card>

      {/* Category Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('users.detail.sections.filesByType')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <CategoryCard
            icon={Image}
            label={t('users.detail.fileTypes.images')}
            count={file_usage.image_count}
            sizeBytes={file_usage.image_size_bytes}
            color="bg-blue-500"
          />
          <CategoryCard
            icon={Video}
            label={t('users.detail.fileTypes.videos')}
            count={file_usage.video_count}
            sizeBytes={file_usage.video_size_bytes}
            color="bg-purple-500"
          />
          <CategoryCard
            icon={FileText}
            label={t('users.detail.fileTypes.documents')}
            count={file_usage.document_count}
            sizeBytes={file_usage.document_size_bytes}
            color="bg-green-500"
          />
          <CategoryCard
            icon={Music}
            label={t('users.detail.fileTypes.audio')}
            count={file_usage.audio_count}
            sizeBytes={file_usage.audio_size_bytes}
            color="bg-orange-500"
          />
          <CategoryCard
            icon={File}
            label={t('users.detail.fileTypes.other')}
            count={file_usage.other_count}
            sizeBytes={file_usage.other_size_bytes}
            color="bg-gray-500"
          />
        </CardContent>
      </Card>
    </div>
  )
}
