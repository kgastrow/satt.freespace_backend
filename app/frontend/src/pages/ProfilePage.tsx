import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useAppSelector } from '@/store/hooks'
import { useGetCurrentUserQuery } from '@/features/auth/authApi'
import { useUploadAvatarMutation, useDeleteAvatarMutation } from '@/features/user/userApi'
import { PageHeader } from '@/components/PageHeader'
import { getErrorMessage } from '@/types/api'
import { ImpersonationHistorySection } from '@/components/profile/ImpersonationHistorySection'
import { EditProfileDialog } from '@/components/profile/EditProfileDialog'
import { UserTypesSection } from '@/features/onboarding/UserTypesSection'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CardSkeleton } from '@/components/skeletons'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Camera, Trash2, Upload, Pencil, CheckCircle, XCircle } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'

export function ProfilePage() {
  const { t } = useTranslation(['settings', 'backend'])
  const { user } = useAppSelector((state) => state.auth)
  // Type assertion to handle avatar_url and phone_verified which may not be in generated types yet
  const { data: currentUserData, isLoading: isLoadingUser } = useGetCurrentUserQuery()
  const currentUser = currentUserData as (typeof currentUserData & { avatar_url?: string | null; phone_verified?: boolean }) | undefined
  const [uploadAvatar, { isLoading: isUploadingAvatar }] = useUploadAvatarMutation()
  const [deleteAvatar, { isLoading: isDeletingAvatar }] = useDeleteAvatarMutation()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [editDialogOpen, setEditDialogOpen] = useState(false)

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    // Validate file type
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if (!validTypes.includes(file.type)) {
      toast.error(t('profile.avatar.errors.invalidType'))
      return
    }

    // Validate file size (5MB)
    const maxSize = 5 * 1024 * 1024
    if (file.size > maxSize) {
      toast.error(t('profile.avatar.errors.tooLarge'))
      return
    }

    setSelectedFile(file)
    const reader = new FileReader()
    reader.onloadend = () => {
      setPreviewUrl(reader.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    try {
      await uploadAvatar(selectedFile).unwrap()
      toast.success(t('profile.avatar.messages.uploadSuccess'))
      setSelectedFile(null)
      setPreviewUrl(null)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const handleCancelUpload = () => {
    setSelectedFile(null)
    setPreviewUrl(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleDelete = async () => {
    try {
      await deleteAvatar().unwrap()
      toast.success(t('profile.avatar.messages.deleteSuccess'))
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const getInitials = () => {
    const first = currentUser?.first_name || user?.first_name || ''
    const last = currentUser?.last_name || user?.last_name || ''
    return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase()
  }

  const formatPhoneNumber = (phone: string | null | undefined) => {
    if (!phone) return '-'
    return phone
  }

  if (isLoadingUser) {
    return (
      <div className="space-y-6">
        <PageHeader title={t('profile.title')} description={t('profile.description')} />
        <div className="grid gap-6 md:grid-cols-2">
          <CardSkeleton variant="default" />
          <CardSkeleton variant="default" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t('profile.title')} description={t('profile.description')} />

      {/* Avatar Upload */}
      <Card>
        <CardHeader>
          <CardTitle>{t('profile.avatar.title')}</CardTitle>
          <CardDescription>{t('profile.avatar.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
            {/* Avatar Display */}
            <div className="relative">
              <Avatar className="size-24" data-testid="profile-avatar">
                <AvatarImage
                  src={previewUrl || currentUser?.avatar_url || undefined}
                  alt={getInitials()}
                />
                <AvatarFallback className="text-2xl">{getInitials()}</AvatarFallback>
              </Avatar>
              {!selectedFile && !previewUrl && (
                <Button
                  type="button"
                  size="icon"
                  variant="secondary"
                  className="absolute -bottom-2 -right-2 size-8 rounded-full"
                  onClick={handleUploadClick}
                  disabled={isUploadingAvatar || isDeletingAvatar}
                >
                  <Camera className="size-4" />
                </Button>
              )}
            </div>

            {/* Upload Controls */}
            <div className="flex-1 space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                onChange={handleFileSelect}
                className="hidden"
                data-testid="avatar-file-input"
              />

              {selectedFile ? (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {t('profile.avatar.previewLabel')}: {selectedFile.name}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      onClick={handleUpload}
                      disabled={isUploadingAvatar}
                      size="sm"
                    >
                      {isUploadingAvatar ? (
                        <>
                          <Upload className="mr-2 size-4 animate-spin" />
                          {t('profile.avatar.buttons.uploading')}
                        </>
                      ) : (
                        <>
                          <Upload className="mr-2 size-4" />
                          {t('profile.avatar.buttons.upload')}
                        </>
                      )}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleCancelUpload}
                      disabled={isUploadingAvatar}
                      size="sm"
                    >
                      {t('profile.avatar.buttons.cancel')}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {t('profile.avatar.uploadHint')}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleUploadClick}
                      disabled={isUploadingAvatar || isDeletingAvatar}
                      size="sm"
                    >
                      <Upload className="mr-2 size-4" />
                      {t('profile.avatar.buttons.choose')}
                    </Button>
                    {currentUser?.avatar_url && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            disabled={isUploadingAvatar || isDeletingAvatar}
                          >
                            <Trash2 className="mr-2 size-4" />
                            {t('profile.avatar.buttons.remove')}
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              {t('profile.avatar.confirmDelete.title')}
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              {t('profile.avatar.confirmDelete.description')}
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>
                              {t('profile.avatar.confirmDelete.cancel')}
                            </AlertDialogCancel>
                            <AlertDialogAction
                              onClick={handleDelete}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              {isDeletingAvatar
                                ? t('profile.avatar.buttons.deleting')
                                : t('profile.avatar.confirmDelete.confirm')}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Profile Information - Read-only with Edit button */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div className="space-y-1.5">
              <CardTitle>{t('profile.sections.profileInfo.title')}</CardTitle>
              <CardDescription>{t('profile.sections.profileInfo.description')}</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setEditDialogOpen(true)}
              data-testid="edit-profile-button"
            >
              <Pencil className="size-4" />
              <span className="sr-only">{t('profile.editDialog.title')}</span>
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* First Name */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                {t('profile.fields.firstName')}
              </p>
              <p className="text-sm">
                {currentUser?.first_name || user?.first_name || '-'}
              </p>
            </div>

            {/* Last Name */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                {t('profile.fields.lastName')}
              </p>
              <p className="text-sm">
                {currentUser?.last_name || user?.last_name || '-'}
              </p>
            </div>

            {/* Email */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                {t('profile.fields.email')}
              </p>
              <p className="text-sm">
                {currentUser?.email || user?.email || '-'}
              </p>
              <Link
                to="/settings/security/email"
                className="text-xs text-primary hover:underline"
              >
                {t('profile.editDialog.changeEmailLink')}
              </Link>
            </div>

            {/* Phone */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                {t('profile.fields.phone')}
              </p>
              <div className="flex items-center gap-2">
                <p className="text-sm">
                  {formatPhoneNumber(currentUser?.phone)}
                </p>
                {currentUser?.phone && (
                  currentUser?.phone_verified ? (
                    <Badge variant="outline" className="text-green-600 border-green-600">
                      <CheckCircle className="mr-1 size-3" />
                      {t('profile.badges.verified')}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-yellow-600 border-yellow-600">
                      <XCircle className="mr-1 size-3" />
                      {t('profile.badges.unverified')}
                    </Badge>
                  )
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Account Information (Read-only) */}
        <Card>
          <CardHeader>
            <CardTitle>{t('profile.sections.accountInfo.title')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-2">
                {t('profile.fields.organization')}
              </p>
              <p className="text-sm">
                {currentUser?.organization?.name || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-2">
                {t('profile.fields.roles')}
              </p>
              <div className="flex flex-wrap gap-2">
                {currentUser?.is_admin && <Badge>{t('profile.badges.admin')}</Badge>}
                {currentUser?.roles && currentUser.roles.length > 0 ? (
                  currentUser.roles.map((role) => (
                    <Badge key={role.id} variant="secondary">{role.name}</Badge>
                  ))
                ) : (
                  !currentUser?.is_admin && (
                    <span className="text-muted-foreground">{t('profile.messages.noRoles')}</span>
                  )
                )}
              </div>
            </div>
            {/* User Types */}
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-2">
                {t('profile.fields.userTypes')}
              </p>
              <UserTypesSection />
            </div>
          </CardContent>
        </Card>

        {/* Impersonation History - conditionally rendered based on user's history */}
        <ImpersonationHistorySection />
      </div>

      {/* Edit Profile Dialog */}
      {currentUser && (
        <EditProfileDialog
          open={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          currentUser={{
            first_name: currentUser.first_name,
            last_name: currentUser.last_name,
            email: currentUser.email,
            phone: currentUser.phone,
            phone_verified: currentUser.phone_verified,
          }}
        />
      )}
    </div>
  )
}
