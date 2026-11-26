import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { GalleryVerticalEnd, Link2, AlertCircle, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useConfirmAccountLinkMutation } from '@/features/auth/ssoApi'
import type { ConfirmLinkRequest } from '@/types/sso'
import {
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
} from '@/features/auth/authApi'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { setCredentials } from '@/features/auth/authSlice'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface LocationState {
  email?: string
  provider?: string
}

export function SSOConfirmLinkPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useAppDispatch()
  const [confirmLink, { isLoading }] = useConfirmAccountLinkMutation()
  const [fetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [fetchUserPermissions] = useLazyGetUserPermissionsQuery()
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')

  // A caller who is already signed in as the existing account proves control
  // with their bearer token, so the password field is not shown to them.
  const isAuthenticated = useAppSelector((s) => s.auth.isAuthenticated)

  const state = location.state as LocationState | null
  const linkToken = sessionStorage.getItem('sso_link_token')
  const email = state?.email
  const provider = state?.provider

  // Redirect to login if no link token
  useEffect(() => {
    if (!linkToken) {
      navigate('/login')
    }
  }, [linkToken, navigate])

  const handleConfirmLink = async () => {
    if (!linkToken) return

    if (!isAuthenticated && !password) {
      setError(t('auth:sso.linkPasswordRequired'))
      return
    }

    setError(null)

    // Proof of the existing account: the bearer session when there is one,
    // otherwise the re-entered password. `password` is omitted entirely for a
    // signed-in caller so the request carries no credential it does not need.
    const payload: ConfirmLinkRequest = isAuthenticated
      ? { link_token: linkToken }
      : { link_token: linkToken, password }

    try {
      const result = await confirmLink(payload).unwrap()

      // Refresh token is in httpOnly cookie
      sessionStorage.removeItem('sso_link_token')
      sessionStorage.removeItem('sso_provider')

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

      toast.success(t('auth:sso.linkSuccess'), { category: 'auth' })
      navigate('/dashboard')
    } catch (err) {
      setError(getLinkErrorMessage(err))
    }
  }

  /**
   * Map the backend's refusal onto something the user can act on. The proof
   * requirement is new, so a stale client hitting an upgraded backend lands
   * here rather than on a silent failure.
   */
  function getLinkErrorMessage(err: unknown): string {
    const apiError = err as {
      status?: number
      data?: { detail_code?: string; detail?: { detail_code?: string } }
    }
    const detailCode =
      apiError?.data?.detail_code ?? apiError?.data?.detail?.detail_code

    // `detail_code` is the contract, so every code is matched before any
    // status is. The backend now separates the two refusals by status as well
    // (403 for a rejected proof, 401 for a missing one), but the codes stay
    // authoritative: an older backend answers both with 401, and a status-first
    // branch would then tell someone who simply mistyped their password to go
    // and sign in instead.
    if (detailCode === 'auth.invalid_password') {
      return t('auth:sso.linkPasswordInvalid')
    }
    if (detailCode === 'sso.link_proof_required') {
      return t('auth:sso.linkProofRequired')
    }
    if (detailCode === 'sso.link_attempts_exceeded') {
      return t('backend:sso.link_attempts_exceeded')
    }
    if (detailCode === 'auth.ip_blocked') {
      return t('backend:auth.ip_blocked')
    }
    if (detailCode === 'sso.link_verification_unavailable') {
      return t('auth:sso.linkUnavailable')
    }

    // Belt and braces for an unexpected error shape - a proxy's own 401/403/503,
    // or a body with no detail_code at all - so the user still gets something
    // actionable rather than the generic failure.
    if (apiError?.status === 401) {
      return t('auth:sso.linkProofRequired')
    }
    if (apiError?.status === 403) {
      return t('auth:sso.linkPasswordInvalid')
    }
    if (apiError?.status === 503) {
      return t('auth:sso.linkUnavailable')
    }
    return t('auth:sso.linkError')
  }

  const handleCancel = () => {
    sessionStorage.removeItem('sso_link_token')
    sessionStorage.removeItem('sso_provider')
    navigate('/login')
  }

  const getProviderDisplayName = (providerKey: string | undefined) => {
    if (!providerKey) return 'SSO'
    const names: Record<string, string> = {
      google: 'Google',
    }
    return names[providerKey] || providerKey
  }

  if (!linkToken) {
    return null
  }

  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-center gap-2 md:justify-start">
          <Link to="/" className="flex items-center gap-2 font-medium">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GalleryVerticalEnd className="size-4" />
            </div>
            {t('common:app.name')}
          </Link>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <Card className="w-full max-w-md">
            <CardHeader className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <Link2 className="h-6 w-6 text-primary" />
              </div>
              <CardTitle>{t('auth:sso.linkTitle')}</CardTitle>
              <CardDescription>
                {t('auth:sso.accountExists', { email: email || '' })}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>{t('common:error')}</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <p className="text-sm text-muted-foreground">
                {t('auth:sso.confirmLink', {
                  provider: getProviderDisplayName(provider),
                })}
              </p>
              <p className="text-sm text-muted-foreground">
                {t('auth:sso.linkDescription')}
              </p>
              {isAuthenticated ? (
                <p className="text-sm text-muted-foreground">
                  {t('auth:sso.linkSignedInAs', { email: email || '' })}
                </p>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="link-password">
                    {t('auth:sso.linkPasswordLabel', { email: email || '' })}
                  </Label>
                  <Input
                    id="link-password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !isLoading) {
                        handleConfirmLink()
                      }
                    }}
                    placeholder={t('auth:sso.linkPasswordPlaceholder')}
                    disabled={isLoading}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('auth:sso.linkPasswordHelp')}
                  </p>
                </div>
              )}
            </CardContent>
            <CardFooter className="flex flex-col gap-3">
              <Button
                className="w-full"
                onClick={handleConfirmLink}
                disabled={isLoading || (!isAuthenticated && !password)}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t('auth:sso.linking')}
                  </>
                ) : (
                  t('auth:sso.linkAccount')
                )}
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={handleCancel}
                disabled={isLoading}
              >
                {t('common:cancel')}
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
      <div className="relative hidden bg-muted lg:block">
        <img
          src="/placeholder.svg"
          alt={t('auth:login.coverAlt')}
          className="absolute inset-0 h-full w-full object-cover dark:brightness-[0.2] dark:grayscale"
        />
      </div>
    </div>
  )
}
