import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import {
  Mail,
  Phone,
  Calendar,
  Clock,
  Bell,
  UserCircle,
  AlertCircle,
  CheckCircle,
  XCircle,
  Save,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { toast } from '@/lib/toast'
import {
  useUpdateUserMutation,
  useUpdateUserNotificationPreferencesMutation,
  type UserFullDetail,
} from '@/features/users/usersApi'
import { UserRolesCard } from './UserRolesCard'
import { UserTypesCard } from './UserTypesCard'

interface UserOverviewSectionProps {
  user: UserFullDetail
  isSuperAdmin?: boolean
}

export function UserOverviewSection({ user, isSuperAdmin = false }: UserOverviewSectionProps) {
  const { t } = useTranslation('admin')

  // Inline editing state
  const [editedFields, setEditedFields] = useState({
    first_name: user.first_name || '',
    last_name: user.last_name || '',
    email: user.email,
    phone: user.phone || '',
  })
  const [hasChanges, setHasChanges] = useState(false)

  const [updateUser, { isLoading: isUpdating }] = useUpdateUserMutation()
  const [updateNotificationPrefs, { isLoading: isUpdatingPrefs }] =
    useUpdateUserNotificationPreferencesMutation()

  const formatDate = (dateString?: string | null) => {
    if (!dateString) return '-'
    return format(new Date(dateString), 'PPp')
  }

  const handleFieldChange = (field: string, value: string) => {
    setEditedFields((prev) => ({ ...prev, [field]: value }))
    setHasChanges(true)
  }

  const handleSaveChanges = async () => {
    try {
      await updateUser({
        id: user.id,
        data: {
          first_name: editedFields.first_name || undefined,
          last_name: editedFields.last_name || undefined,
          email: editedFields.email !== user.email ? editedFields.email : undefined,
          phone: editedFields.phone !== (user.phone || '') ? (editedFields.phone || null) : undefined,
        },
      }).unwrap()
      toast.success(t('users.detail.saved'))
      setHasChanges(false)
    } catch {
      toast.error(t('users.detail.saveFailed'))
    }
  }

  const handleNotificationToggle = async (channel: string, enabled: boolean) => {
    try {
      await updateNotificationPrefs({
        userId: user.id,
        data: { [`${channel}_enabled`]: enabled },
      }).unwrap()
      toast.success(t('users.detail.notificationPrefSaved'))
    } catch {
      toast.error(t('users.detail.notificationPrefFailed'))
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Basic Info with Inline Editing */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <div className="flex items-center gap-2">
              <UserCircle className="h-5 w-5" />
              {t('users.detail.sections.basicInfo')}
            </div>
            {hasChanges && (
              <Button size="sm" onClick={handleSaveChanges} disabled={isUpdating}>
                {isUpdating ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <Save className="h-4 w-4 mr-1" />
                )}
                {t('common.save')}
              </Button>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* First Name */}
          <div className="space-y-2">
            <Label htmlFor="first_name">{t('users.detail.fields.firstName')}</Label>
            <Input
              id="first_name"
              value={editedFields.first_name}
              onChange={(e) => handleFieldChange('first_name', e.target.value)}
              placeholder={t('users.detail.fields.firstNamePlaceholder')}
            />
          </div>

          {/* Last Name */}
          <div className="space-y-2">
            <Label htmlFor="last_name">{t('users.detail.fields.lastName')}</Label>
            <Input
              id="last_name"
              value={editedFields.last_name}
              onChange={(e) => handleFieldChange('last_name', e.target.value)}
              placeholder={t('users.detail.fields.lastNamePlaceholder')}
            />
          </div>

          {/* Email */}
          <div className="space-y-2">
            <Label htmlFor="email" className="flex items-center gap-2">
              <Mail className="h-4 w-4" />
              {t('users.detail.fields.email')}
              {user.email_verified ? (
                <Badge variant="outline" className="text-green-600 border-green-600 text-xs">
                  <CheckCircle className="h-3 w-3 mr-1" />
                  {t('users.detail.verified')}
                </Badge>
              ) : (
                <Badge variant="outline" className="text-amber-600 border-amber-600 text-xs">
                  <XCircle className="h-3 w-3 mr-1" />
                  {t('users.detail.unverified')}
                </Badge>
              )}
            </Label>
            <Input
              id="email"
              type="email"
              value={editedFields.email}
              onChange={(e) => handleFieldChange('email', e.target.value)}
            />
            {!user.email_deliverable && (
              <p className="text-xs text-destructive">{t('users.detail.emailUndeliverable')}</p>
            )}
          </div>

          {/* Phone */}
          <div className="space-y-2">
            <Label htmlFor="phone" className="flex items-center gap-2">
              <Phone className="h-4 w-4" />
              {t('users.detail.fields.phone')}
              {user.phone && (
                user.phone_verified ? (
                  <Badge variant="outline" className="text-green-600 border-green-600 text-xs">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    {t('users.detail.verified')}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-amber-600 border-amber-600 text-xs">
                    <XCircle className="h-3 w-3 mr-1" />
                    {t('users.detail.unverified')}
                  </Badge>
                )
              )}
            </Label>
            <Input
              id="phone"
              type="tel"
              value={editedFields.phone}
              onChange={(e) => handleFieldChange('phone', e.target.value)}
              placeholder={t('users.detail.fields.phonePlaceholder')}
            />
          </div>

          <Separator />

          {/* Read-only info */}
          <div className="flex items-start gap-3">
            <Calendar className="h-4 w-4 mt-0.5 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{t('users.detail.fields.joined')}</p>
              <p className="text-sm text-muted-foreground">{formatDate(user.created_time)}</p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Clock className="h-4 w-4 mt-0.5 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{t('users.detail.fields.lastUpdated')}</p>
              <p className="text-sm text-muted-foreground">{formatDate(user.updated_time)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Roles Card */}
      <UserRolesCard user={user} />

      {/* User Types Card */}
      <UserTypesCard user={user} isSuperAdmin={isSuperAdmin} />

      {/* Suspension Info (if suspended) */}
      {user.suspension_status === 'suspended' && user.suspension_info && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              {t('users.detail.sections.suspensionInfo')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {user.suspension_info.suspension_reason && (
              <div>
                <p className="text-sm font-medium">{t('users.detail.fields.suspensionReason')}</p>
                <p className="text-sm text-muted-foreground">{user.suspension_info.suspension_reason}</p>
              </div>
            )}
            <div>
              <p className="text-sm font-medium">{t('users.detail.fields.suspendedAt')}</p>
              <p className="text-sm text-muted-foreground">
                {formatDate(user.suspension_info.suspended_time)}
              </p>
            </div>
            {user.suspension_info.suspended_by_name && (
              <div>
                <p className="text-sm font-medium">{t('users.detail.fields.suspendedBy')}</p>
                <p className="text-sm text-muted-foreground">{user.suspension_info.suspended_by_name}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Notification Preferences with Editable Toggles */}
      {user.notification_preferences && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-5 w-5" />
              {t('users.detail.sections.notificationPrefs')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="email-notif" className="flex items-center gap-2 cursor-pointer">
                  {t('users.detail.notifications.email')}
                </Label>
                <Switch
                  id="email-notif"
                  checked={user.notification_preferences.email_enabled}
                  onCheckedChange={(checked) => handleNotificationToggle('email', checked)}
                  disabled={isUpdatingPrefs || !isSuperAdmin}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="sms-notif" className="flex items-center gap-2 cursor-pointer">
                  {t('users.detail.notifications.sms')}
                </Label>
                <Switch
                  id="sms-notif"
                  checked={user.notification_preferences.sms_enabled}
                  onCheckedChange={(checked) => handleNotificationToggle('sms', checked)}
                  disabled={isUpdatingPrefs || !isSuperAdmin}
                />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="in-app-notif" className="flex items-center gap-2 cursor-pointer">
                  {t('users.detail.notifications.inApp')}
                </Label>
                <Switch
                  id="in-app-notif"
                  checked={user.notification_preferences.in_app_enabled}
                  onCheckedChange={(checked) => handleNotificationToggle('in_app', checked)}
                  disabled={isUpdatingPrefs || !isSuperAdmin}
                />
              </div>
            </div>
            {!isSuperAdmin && (
              <p className="text-xs text-muted-foreground mt-4">
                {t('users.detail.notificationPrefsReadOnly')}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
