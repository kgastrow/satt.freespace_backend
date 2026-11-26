import { useState, useEffect, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { getErrorMessage } from '@/types/api'
import { useUpdateProfileMutation } from '@/features/user/userApi'
import {
  useSendPhoneOTPMutation,
  useVerifyPhoneOTPMutation,
} from '@/features/user/phoneVerificationApi'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { CheckCircle } from 'lucide-react'

// Schema for the profile form
const profileSchema = z.object({
  firstName: z.string().min(1, 'First name is required'),
  lastName: z.string().min(1, 'Last name is required'),
  email: z.string().email('Invalid email address'),
  phone: z.string().optional(),
})

type ProfileFormData = z.infer<typeof profileSchema>

// State machine for dialog flow
type DialogState =
  | 'idle'
  | 'phoneVerification'

export interface EditProfileDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentUser: {
    first_name?: string | null
    last_name?: string | null
    email: string
    phone?: string | null
    phone_verified?: boolean
  }
}

export function EditProfileDialog({
  open,
  onOpenChange,
  currentUser,
}: EditProfileDialogProps) {
  const { t } = useTranslation(['settings', 'backend'])
  const [dialogState, setDialogState] = useState<DialogState>('idle')
  const [pendingPhone, setPendingPhone] = useState<string | null>(null)
  const [otpCode, setOtpCode] = useState('')
  const [resendCountdown, setResendCountdown] = useState(0)

  const [updateProfile, { isLoading: isUpdatingProfile }] = useUpdateProfileMutation()
  const [sendPhoneOTP, { isLoading: isSendingOTP }] = useSendPhoneOTPMutation()
  const [verifyPhoneOTP, { isLoading: isVerifyingOTP }] = useVerifyPhoneOTPMutation()

  const profileForm = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      firstName: currentUser?.first_name || '',
      lastName: currentUser?.last_name || '',
      email: currentUser?.email || '',
      phone: currentUser?.phone || '',
    },
  })

  // Reset form when currentUser changes (not when dialog opens - that's handled by onOpenChange)
  useEffect(() => {
    if (open && currentUser) {
      profileForm.reset({
        firstName: currentUser?.first_name || '',
        lastName: currentUser?.last_name || '',
        email: currentUser?.email || '',
        phone: currentUser?.phone || '',
      })
    }
  }, [currentUser, profileForm, open])

  // Handle dialog open state changes
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (newOpen) {
      // Reset state when opening
      setDialogState('idle')
      setOtpCode('')
      setPendingPhone(null)
      profileForm.reset({
        firstName: currentUser?.first_name || '',
        lastName: currentUser?.last_name || '',
        email: currentUser?.email || '',
        phone: currentUser?.phone || '',
      })
    }
    onOpenChange(newOpen)
  }, [currentUser, onOpenChange, profileForm])

  // Countdown timer for resend
  useEffect(() => {
    if (resendCountdown > 0) {
      const timer = setTimeout(() => setResendCountdown(resendCountdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCountdown])

  const handleClose = useCallback(() => {
    setDialogState('idle')
    setOtpCode('')
    setPendingPhone(null)
    onOpenChange(false)
  }, [onOpenChange])

  const onProfileSubmit = async (data: ProfileFormData) => {
    const phoneChanged = data.phone !== (currentUser?.phone || '')
    const emailChanged = data.email !== currentUser?.email

    // If email changed, inform user about the email change flow
    if (emailChanged) {
      toast.error(t('profile.editDialog.emailChangeNote'))
      return
    }

    try {
      // Update name and other profile data first
      await updateProfile({
        first_name: data.firstName,
        last_name: data.lastName,
      }).unwrap()

      // If phone changed, start phone verification flow
      if (phoneChanged && data.phone) {
        setPendingPhone(data.phone)

        try {
          await sendPhoneOTP({ phone: data.phone }).unwrap()
          setResendCountdown(60)
          setDialogState('phoneVerification')
          toast.success(t('profile.phoneVerification.codeSent'))
        } catch (error: unknown) {
          toast.error(getErrorMessage(error, t))
          // Name was saved, close dialog but notify user
          toast.success(t('profile.messages.profileUpdateSuccess'))
          handleClose()
        }
      } else {
        toast.success(t('profile.messages.profileUpdateSuccess'))
        handleClose()
      }
    } catch (error: unknown) {
      profileForm.setError('root', { message: getErrorMessage(error, t) })
    }
  }

  const handleVerifyOTP = async () => {
    if (!pendingPhone || otpCode.length !== 6) return

    try {
      await verifyPhoneOTP({
        phone: pendingPhone,
        otp_code: otpCode,
      }).unwrap()
      toast.success(t('profile.phoneVerification.success'))
      handleClose()
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const handleResendOTP = async () => {
    if (!pendingPhone || resendCountdown > 0) return

    try {
      await sendPhoneOTP({ phone: pendingPhone }).unwrap()
      setResendCountdown(60)
      setOtpCode('')
      toast.success(t('profile.phoneVerification.codeSent'))
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const renderIdleState = () => (
    <Form {...profileForm}>
      <form onSubmit={profileForm.handleSubmit(onProfileSubmit)} className="space-y-4">
        {profileForm.formState.errors.root && (
          <Alert variant="destructive">
            <AlertDescription>
              {profileForm.formState.errors.root.message}
            </AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={profileForm.control}
            name="firstName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('profile.fields.firstName')}</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={profileForm.control}
            name="lastName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('profile.fields.lastName')}</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={profileForm.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('profile.fields.email')}</FormLabel>
              <FormControl>
                <Input type="email" {...field} disabled />
              </FormControl>
              <p className="text-xs text-muted-foreground">
                {t('profile.editDialog.emailChangeHint')}
              </p>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={profileForm.control}
          name="phone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('profile.fields.phone')}</FormLabel>
              <FormControl>
                <Input type="tel" placeholder="+1234567890" {...field} />
              </FormControl>
              <p className="text-xs text-muted-foreground">
                {t('profile.editDialog.phoneChangeHint')}
              </p>
              <FormMessage />
            </FormItem>
          )}
        />

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose}>
            {t('profile.editDialog.buttons.cancel')}
          </Button>
          <Button type="submit" disabled={isUpdatingProfile || isSendingOTP}>
            {isUpdatingProfile || isSendingOTP
              ? t('profile.editDialog.buttons.saving')
              : t('profile.editDialog.buttons.save')}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  )

  const renderPhoneVerificationState = () => (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <CheckCircle className="size-4 text-green-500" />
        {t('profile.phoneVerification.nameSaved')}
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium">{t('profile.phoneVerification.title')}</p>
        <p className="text-sm text-muted-foreground">
          {t('profile.phoneVerification.description', { phone: pendingPhone })}
        </p>
      </div>

      <div className="flex justify-center">
        <InputOTP
          maxLength={6}
          value={otpCode}
          onChange={setOtpCode}
          data-testid="phone-otp-input"
        >
          <InputOTPGroup>
            <InputOTPSlot index={0} />
            <InputOTPSlot index={1} />
            <InputOTPSlot index={2} />
            <InputOTPSlot index={3} />
            <InputOTPSlot index={4} />
            <InputOTPSlot index={5} />
          </InputOTPGroup>
        </InputOTP>
      </div>

      <div className="text-center text-sm text-muted-foreground">
        {resendCountdown > 0 ? (
          <span>{t('profile.phoneVerification.resendCountdown', { seconds: resendCountdown })}</span>
        ) : (
          <span>
            {t('profile.phoneVerification.noCode')}{' '}
            <Button
              variant="link"
              className="h-auto p-0"
              onClick={handleResendOTP}
              disabled={isSendingOTP}
            >
              {isSendingOTP
                ? t('profile.phoneVerification.buttons.resending')
                : t('profile.phoneVerification.buttons.resend')}
            </Button>
          </span>
        )}
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={handleClose}>
          {t('profile.editDialog.buttons.cancel')}
        </Button>
        <Button
          onClick={handleVerifyOTP}
          disabled={otpCode.length !== 6 || isVerifyingOTP}
        >
          {isVerifyingOTP
            ? t('profile.phoneVerification.buttons.verifying')
            : t('profile.phoneVerification.buttons.verify')}
        </Button>
      </DialogFooter>
    </div>
  )

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {dialogState === 'phoneVerification'
              ? t('profile.phoneVerification.title')
              : t('profile.editDialog.title')}
          </DialogTitle>
          <DialogDescription>
            {dialogState === 'phoneVerification'
              ? t('profile.phoneVerification.description', { phone: pendingPhone })
              : t('profile.editDialog.description')}
          </DialogDescription>
        </DialogHeader>

        {dialogState === 'idle' && renderIdleState()}
        {dialogState === 'phoneVerification' && renderPhoneVerificationState()}
      </DialogContent>
    </Dialog>
  )
}
