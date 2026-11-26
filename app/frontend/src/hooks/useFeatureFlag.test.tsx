import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore } from '@reduxjs/toolkit'
import { useFeatureFlag } from './useFeatureFlag'
import featureFlagsReducer from '@/features/featureFlags/featureFlagsSlice'
import authReducer from '@/features/auth/authSlice'

describe('useFeatureFlag', () => {
  it('returns false when flag does not exist', () => {
    const store = configureStore({
      reducer: {
        featureFlags: featureFlagsReducer,
        auth: authReducer,
      },
    })

    const { result } = renderHook(() => useFeatureFlag('non-existent-flag'), {
      wrapper: ({ children }) => <Provider store={store}>{children}</Provider>,
    })

    expect(result.current).toBe(false)
  })

  it('returns true when flag is enabled', () => {
    const store = configureStore({
      reducer: {
        featureFlags: featureFlagsReducer,
        auth: authReducer,
      },
      preloadedState: {
        featureFlags: {
          flags: {
            'test-flag': true,
          },
          isLoaded: true,
        },
      },
    })

    const { result } = renderHook(() => useFeatureFlag('test-flag'), {
      wrapper: ({ children }) => <Provider store={store}>{children}</Provider>,
    })

    expect(result.current).toBe(true)
  })

  it('returns false when flag is disabled', () => {
    const store = configureStore({
      reducer: {
        featureFlags: featureFlagsReducer,
        auth: authReducer,
      },
      preloadedState: {
        featureFlags: {
          flags: {
            'test-flag': false,
          },
          isLoaded: true,
        },
      },
    })

    const { result } = renderHook(() => useFeatureFlag('test-flag'), {
      wrapper: ({ children }) => <Provider store={store}>{children}</Provider>,
    })

    expect(result.current).toBe(false)
  })

  it('handles multiple flags correctly', () => {
    const store = configureStore({
      reducer: {
        featureFlags: featureFlagsReducer,
        auth: authReducer,
      },
      preloadedState: {
        featureFlags: {
          flags: {
            'flag-enabled': true,
            'flag-disabled': false,
          },
          isLoaded: true,
        },
      },
    })

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <Provider store={store}>{children}</Provider>
    )

    const { result: result1 } = renderHook(() => useFeatureFlag('flag-enabled'), {
      wrapper,
    })
    const { result: result2 } = renderHook(() => useFeatureFlag('flag-disabled'), {
      wrapper,
    })

    expect(result1.current).toBe(true)
    expect(result2.current).toBe(false)
  })
})
