import { useEffect } from 'react'
import { claimUpdateDeferral, releaseUpdateDeferral } from '@/lib/deferUpdate'

/**
 * Hold off an automatic version swap while `active` is true.
 *
 * Use it wherever a reload would cost the user something they cannot get back:
 * a half-filled form, an in-flight upload, a wizard part-way through. The claim
 * is released on unmount, so a component that navigates away mid-edit does not
 * pin the app to an old build forever.
 *
 * `reason` must be unique per claimant — it is the identity of the claim, so two
 * mounted copies sharing one string release each other. Prefer something
 * traceable, e.g. `form:organization-settings`.
 */
export function useDeferUpdate(active: boolean, reason: string): void {
  useEffect(() => {
    if (!active) return
    claimUpdateDeferral(reason)
    return () => releaseUpdateDeferral(reason)
  }, [active, reason])
}
