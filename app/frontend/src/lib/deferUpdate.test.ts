/**
 * deferUpdate: the registry the auto-apply policy consults before swapping a
 * build in. A claim that leaks would pin the app to an old build forever, so
 * release semantics matter as much as claim.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  claimUpdateDeferral,
  hasUpdateDeferrals,
  listUpdateDeferrals,
  releaseUpdateDeferral,
  resetUpdateDeferrals,
  subscribeUpdateDeferrals,
} from './deferUpdate'

beforeEach(() => {
  resetUpdateDeferrals()
})

describe('deferUpdate', () => {
  it('is clear when nothing has claimed', () => {
    expect(hasUpdateDeferrals()).toBe(false)
  })

  it('holds while a claim is outstanding and clears on release', () => {
    claimUpdateDeferral('upload:avatar')
    expect(hasUpdateDeferrals()).toBe(true)

    releaseUpdateDeferral('upload:avatar')
    expect(hasUpdateDeferrals()).toBe(false)
  })

  it('needs every claimant to release before it clears', () => {
    claimUpdateDeferral('upload:avatar')
    claimUpdateDeferral('form:organization-settings')

    releaseUpdateDeferral('upload:avatar')

    expect(hasUpdateDeferrals()).toBe(true)
    expect(listUpdateDeferrals()).toEqual(['form:organization-settings'])
  })

  it('treats a repeated claim as the same claim', () => {
    claimUpdateDeferral('form:organization-settings')
    claimUpdateDeferral('form:organization-settings')

    releaseUpdateDeferral('form:organization-settings')

    expect(hasUpdateDeferrals()).toBe(false)
  })

  it('notifies subscribers on a real change only', () => {
    const listener = vi.fn()
    subscribeUpdateDeferrals(listener)

    claimUpdateDeferral('upload:avatar')
    claimUpdateDeferral('upload:avatar')
    releaseUpdateDeferral('nothing-claimed-this')

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('stops notifying after unsubscribe', () => {
    const listener = vi.fn()
    subscribeUpdateDeferrals(listener)()

    claimUpdateDeferral('upload:avatar')

    expect(listener).not.toHaveBeenCalled()
  })
})
