/**
 * Reasons not to swap the running build out from under the user right now.
 *
 * Anything that would lose work or interrupt something they cannot resume
 * claims a deferral while it is live and releases it afterwards. The auto-apply
 * policy refuses to act while any claim is outstanding; the update badge is
 * unaffected, so the user can still choose to apply.
 *
 * Module-level rather than context, because a claimant — a dirty form, an
 * in-progress upload, anything hoisted above the router — can sit under a
 * different provider from the policy that reads it, and a claim must survive
 * the claimant unmounting mid-navigation only if it explicitly releases.
 */
type Listener = () => void

const deferrals = new Set<string>()
const listeners = new Set<Listener>()

function emit(): void {
  for (const listener of listeners) listener()
}

export function claimUpdateDeferral(reason: string): void {
  if (deferrals.has(reason)) return
  deferrals.add(reason)
  emit()
}

export function releaseUpdateDeferral(reason: string): void {
  if (!deferrals.delete(reason)) return
  emit()
}

/** A boolean, not the set — `useSyncExternalStore` needs a stable snapshot. */
export function hasUpdateDeferrals(): boolean {
  return deferrals.size > 0
}

/** Diagnostics only: what is currently holding an update back. */
export function listUpdateDeferrals(): string[] {
  return [...deferrals]
}

export function subscribeUpdateDeferrals(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Test seam — module state outlives a render tree. */
export function resetUpdateDeferrals(): void {
  deferrals.clear()
  listeners.clear()
}
