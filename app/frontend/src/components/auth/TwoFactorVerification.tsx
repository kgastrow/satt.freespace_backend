import { useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from '@/components/ui/input-otp'
import {
  useVerify2FAMutation,
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
} from '@/features/auth/authApi'
import { clear2FA } from '@/features/auth/authSlice'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { getErrorMessage } from '@/types/api'
import { toast } from '@/lib/toast'

const createTwoFactorSchema = (t: (key: string) => string, useBackupCode: boolean) =>
  z.object({
    code: useBackupCode
      ? z.string().length(8, t('auth:validation.backupCodeLength'))
      : z.string().length(6, t('auth:validation.twoFactorCodeLength')),
  })

type TwoFactorFormData = z.infer<ReturnType<typeof createTwoFactorSchema>>

export function TwoFactorVerification() {
  const { t } = useTranslation(['auth', 'backend'])
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const [useBackupCode, setUseBackupCode] = useState(false)
  const twoFactorToken = useAppSelector((state) => state.auth.twoFactor.token)
  const [verify2FA, { isLoading }] = useVerify2FAMutation()
  const [fetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [fetchUserPermissions] = useLazyGetUserPermissionsQuery()

  const handleBack = () => {
    dispatch(clear2FA())
    navigate('/login')
  }

  const {
    control,
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<TwoFactorFormData>({
    resolver: zodResolver(createTwoFactorSchema(t, useBackupCode)),
    defaultValues: {
      code: '',
    },
  })

  const onSubmit = async (data: TwoFactorFormData) => {
    if (!twoFactorToken) {
      toast.error(t('auth:twoFactor.expiredToken'), { category: 'auth' })
      navigate('/login')
      return
    }

    try {
      await verify2FA({
        two_factor_token: twoFactorToken,
        code: data.code,
      }).unwrap()

      // Fetch user data after successful 2FA verification
      // (tokens are stored via extraReducers, but user/permissions need to be fetched)
      await fetchCurrentUser()
      try {
        await fetchUserPermissions()
      } catch {
        // Permissions fetch failure is non-critical
      }

      navigate('/dashboard')
    } catch (error) {
      toast.error(getErrorMessage(error, t), { category: 'auth' })
    }
  }

  const toggleBackupCode = () => {
    setUseBackupCode(!useBackupCode)
    reset()
  }

  return (
    <div className="w-full max-w-sm">
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-2xl font-bold">{t('auth:twoFactor.title')}</h1>
          <p className="text-balance text-sm text-muted-foreground">
            {t('auth:twoFactor.subtitle')}
          </p>
        </div>
        <div className="grid gap-6">
          <div className="flex flex-col items-center gap-2">
            {useBackupCode ? (
              <>
                <Input
                  id="code"
                  type="text"
                  placeholder={t('auth:twoFactor.backupCodePlaceholder')}
                  autoComplete="one-time-code"
                  autoFocus
                  disabled={isLoading}
                  maxLength={8}
                  className="text-center text-lg tracking-widest"
                  {...register('code')}
                />
              </>
            ) : (
              <Controller
                control={control}
                name="code"
                render={({ field }) => (
                  <InputOTP
                    maxLength={6}
                    value={field.value}
                    onChange={field.onChange}
                    disabled={isLoading}
                    autoFocus
                  >
                    <InputOTPGroup>
                      <InputOTPSlot index={0} className="h-14 w-12 text-xl" />
                      <InputOTPSlot index={1} className="h-14 w-12 text-xl" />
                      <InputOTPSlot index={2} className="h-14 w-12 text-xl" />
                    </InputOTPGroup>
                    <InputOTPSeparator />
                    <InputOTPGroup>
                      <InputOTPSlot index={3} className="h-14 w-12 text-xl" />
                      <InputOTPSlot index={4} className="h-14 w-12 text-xl" />
                      <InputOTPSlot index={5} className="h-14 w-12 text-xl" />
                    </InputOTPGroup>
                  </InputOTP>
                )}
              />
            )}
            {errors.code && (
              <p className="text-sm text-destructive">{errors.code.message}</p>
            )}
          </div>
          <Button type="submit" className="w-full" disabled={isLoading} aria-busy={isLoading}>
            {isLoading ? t('auth:twoFactor.submitting') : t('auth:twoFactor.submit')}
          </Button>
          <div className="flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={toggleBackupCode}
              className="text-sm text-center underline-offset-4 hover:underline text-muted-foreground"
            >
              {useBackupCode
                ? t('auth:twoFactor.backToCode')
                : t('auth:twoFactor.useBackupCode')}
            </button>
            <button
              type="button"
              onClick={handleBack}
              className="text-sm text-center underline-offset-4 hover:underline text-muted-foreground"
            >
              {t('auth:twoFactor.backToLogin')}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
