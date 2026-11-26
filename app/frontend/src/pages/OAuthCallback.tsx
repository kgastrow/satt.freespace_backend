import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  useLazyHandleSSOCallbackQuery,
} from '@/features/auth/ssoApi'
import {
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
} from '@/features/auth/authApi'
import { useAppDispatch } from '@/store/hooks'
import { setCredentials, set2FARequired } from '@/features/auth/authSlice'
import { toast } from '@/lib/toast'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { getSafeRedirectPath } from '@/lib/url-validation'
import type { SSOProvider } from '@/types/sso'
import { isSSOLinkingRequired, isSSOTwoFactorRequired } from '@/types/sso'

// Session storage key for storing the return URL before OAuth redirect
const SSO_RETURN_URL_KEY = 'sso_return_url'

export function OAuthCallback() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const dispatch = useAppDispatch()
  const [handleCallback, { isLoading, error }] = useLazyHandleSSOCallbackQuery()
  const [fetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [fetchUserPermissions] = useLazyGetUserPermissionsQuery()
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    const processCallback = async () => {
      const code = searchParams.get('code')
      const state = searchParams.get('state')
      const errorParam = searchParams.get('error')
      // Retrieve provider from sessionStorage (stored before OAuth redirect)
      const provider = sessionStorage.getItem('sso_provider') as SSOProvider

      if (errorParam) {
        sessionStorage.removeItem('sso_provider')
        setValidationError(`OAuth error: ${errorParam}`)
        return
      }

      if (!code || !state || !provider) {
        sessionStorage.removeItem('sso_provider')
        setValidationError(t('auth:sso.sessionExpired'))
        return
      }

      try {
        const result = await handleCallback({
          provider,
          code,
          state,
        }).unwrap()

        // Check if account linking is required
        if (isSSOLinkingRequired(result)) {
          // Store the link token and redirect to confirmation page
          sessionStorage.setItem('sso_link_token', result.link_token)
          navigate('/sso/confirm-link', {
            state: { email: result.email, provider: result.provider },
          })
          return
        }

        // 2FA challenge - no session exists yet, so this MUST be handled before
        // the access_token branch below (a challenge response has no
        // access_token; storing it would sign the user straight back out, and
        // an SSO-only account has no password path to recover through).
        // The challenge token is stashed in exactly the same place the password
        // login puts it (state.auth.twoFactor), so /login renders the shared
        // TwoFactorVerification screen and POST /auth/verify-2fa completes it.
        if (isSSOTwoFactorRequired(result)) {
          sessionStorage.removeItem('sso_provider')
          // TwoFactorVerification lands on /dashboard, so the stored return URL
          // cannot be honoured - drop it rather than leaving it to leak into
          // the next SSO login.
          sessionStorage.removeItem(SSO_RETURN_URL_KEY)
          dispatch(set2FARequired({ token: result.two_factor_token }))
          toast.info(t('auth:sso.twoFactorRequired'), { category: 'auth' })
          navigate('/login')
          return
        }

        // Normal login success - refresh token is in httpOnly cookie
        sessionStorage.removeItem('sso_provider')

        // Get and validate return URL (SEC-F-004: prevent open redirect)
        const storedReturnUrl = sessionStorage.getItem(SSO_RETURN_URL_KEY)
        sessionStorage.removeItem(SSO_RETURN_URL_KEY)
        const returnUrl = getSafeRedirectPath(storedReturnUrl, '/dashboard')

        dispatch(
          setCredentials({
            token: result.access_token,
          })
        )

        // Fetch user data after tokens are stored
        await fetchCurrentUser()
        try {
          await fetchUserPermissions()
        } catch {
          // Permissions fetch failure is non-critical
        }

        toast.success(t('auth:sso.loginSuccess'), { category: 'auth' })
        navigate(returnUrl)
      } catch {
        sessionStorage.removeItem('sso_provider')
        setValidationError(t('auth:sso.callbackError'))
      }
    }

    processCallback()
  }, [searchParams, handleCallback, fetchCurrentUser, fetchUserPermissions, dispatch, navigate, t])

  if (error || validationError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="w-full max-w-md space-y-4">
          <Alert variant="destructive">
            <AlertTitle>Authentication Failed</AlertTitle>
            <AlertDescription>
              {validationError || 'There was an error completing your SSO login. Please try again.'}
            </AlertDescription>
          </Alert>
          <Button onClick={() => navigate('/login')} className="w-full">
            Return to Login
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <Spinner className="h-8 w-8" />
      <p className="text-muted-foreground">
        {isLoading ? 'Completing sign in...' : 'Processing...'}
      </p>
    </div>
  )
}
