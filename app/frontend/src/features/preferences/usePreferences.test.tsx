/**
 * usePreferences Hook Tests
 *
 * Tests the unified preferences hook including:
 * - Reading preferences from Redux state
 * - Dispatching actions to update preferences
 * - Integration with next-themes and i18next
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore, type EnhancedStore } from '@reduxjs/toolkit'
import type { ReactNode } from 'react'

import { usePreferences } from './usePreferences'
import preferencesReducer, { type PreferencesState } from './preferencesSlice'

// Mock next-themes
const mockSetTheme = vi.fn()
vi.mock('next-themes', () => ({
  useTheme: () => ({
    theme: 'system',
    setTheme: mockSetTheme,
    resolvedTheme: 'light',
  }),
}))

// Mock react-i18next
const mockChangeLanguage = vi.fn().mockResolvedValue(undefined)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'en',
      changeLanguage: mockChangeLanguage,
    },
  }),
}))

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

interface TestState {
  preferences: PreferencesState
}

function createTestStore(preloadedState?: Partial<TestState>): EnhancedStore {
  return configureStore({
    reducer: {
      preferences: preferencesReducer,
    },
    preloadedState: preloadedState as TestState,
  })
}

function createWrapper(store: EnhancedStore) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>
  }
}

describe('usePreferences', () => {
  let store: EnhancedStore

  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
    store = createTestStore({
      preferences: {
        displayMode: 'system',
        language: 'en',
        sidebarCollapsed: false,
        tableColumns: {},
        pwaInstallDismissed: false,
      },
    })
  })

  describe('reading preferences', () => {
    it('returns displayMode from state', () => {
      store = createTestStore({
        preferences: {
          displayMode: 'dark',
          language: 'en',
          sidebarCollapsed: false,
          tableColumns: {},
          pwaInstallDismissed: false,
        },
      })

      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.displayMode).toBe('dark')
    })

    it('returns language from state', () => {
      store = createTestStore({
        preferences: {
          displayMode: 'system',
          language: 'de',
          sidebarCollapsed: false,
          tableColumns: {},
          pwaInstallDismissed: false,
        },
      })

      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.language).toBe('de')
    })

    it('returns sidebarCollapsed from state', () => {
      store = createTestStore({
        preferences: {
          displayMode: 'system',
          language: 'en',
          sidebarCollapsed: true,
          tableColumns: {},
          pwaInstallDismissed: false,
        },
      })

      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.sidebarCollapsed).toBe(true)
    })
  })

  describe('setDisplayMode', () => {
    it('updates Redux state', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setDisplayMode('dark')
      })

      expect(result.current.displayMode).toBe('dark')
    })

    it('calls next-themes setTheme', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setDisplayMode('dark')
      })

      expect(mockSetTheme).toHaveBeenCalledWith('dark')
    })

    it('handles all display modes', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setDisplayMode('light')
      })
      expect(mockSetTheme).toHaveBeenCalledWith('light')

      act(() => {
        result.current.setDisplayMode('dark')
      })
      expect(mockSetTheme).toHaveBeenCalledWith('dark')

      act(() => {
        result.current.setDisplayMode('system')
      })
      expect(mockSetTheme).toHaveBeenCalledWith('system')
    })
  })

  describe('setLanguage', () => {
    it('updates Redux state', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setLanguage('de')
      })

      expect(result.current.language).toBe('de')
    })

    it('calls i18n.changeLanguage', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setLanguage('de')
      })

      expect(mockChangeLanguage).toHaveBeenCalledWith('de')
    })

    it('handles various language codes', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      const languages = ['en', 'de', 'xh', 'zu', 'nso']
      languages.forEach((lang) => {
        act(() => {
          result.current.setLanguage(lang)
        })
        expect(mockChangeLanguage).toHaveBeenCalledWith(lang)
      })
    })
  })

  describe('setSidebarCollapsed', () => {
    it('sets sidebar to collapsed', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setSidebarCollapsed(true)
      })

      expect(result.current.sidebarCollapsed).toBe(true)
    })

    it('sets sidebar to expanded', () => {
      store = createTestStore({
        preferences: {
          displayMode: 'system',
          language: 'en',
          sidebarCollapsed: true,
          tableColumns: {},
          pwaInstallDismissed: false,
        },
      })

      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setSidebarCollapsed(false)
      })

      expect(result.current.sidebarCollapsed).toBe(false)
    })
  })

  describe('toggleSidebar', () => {
    it('toggles sidebar from expanded to collapsed', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.sidebarCollapsed).toBe(false)

      act(() => {
        result.current.toggleSidebar()
      })

      expect(result.current.sidebarCollapsed).toBe(true)
    })

    it('toggles sidebar from collapsed to expanded', () => {
      store = createTestStore({
        preferences: {
          displayMode: 'system',
          language: 'en',
          sidebarCollapsed: true,
          tableColumns: {},
          pwaInstallDismissed: false,
        },
      })

      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.sidebarCollapsed).toBe(true)

      act(() => {
        result.current.toggleSidebar()
      })

      expect(result.current.sidebarCollapsed).toBe(false)
    })

    it('toggles multiple times correctly', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.sidebarCollapsed).toBe(false)

      act(() => {
        result.current.toggleSidebar()
      })
      expect(result.current.sidebarCollapsed).toBe(true)

      act(() => {
        result.current.toggleSidebar()
      })
      expect(result.current.sidebarCollapsed).toBe(false)
    })
  })

  describe('return value structure', () => {
    it('returns all expected properties and functions', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      expect(result.current).toHaveProperty('displayMode')
      expect(result.current).toHaveProperty('language')
      expect(result.current).toHaveProperty('sidebarCollapsed')
      expect(result.current).toHaveProperty('setDisplayMode')
      expect(result.current).toHaveProperty('setLanguage')
      expect(result.current).toHaveProperty('setSidebarCollapsed')
      expect(result.current).toHaveProperty('toggleSidebar')

      expect(typeof result.current.setDisplayMode).toBe('function')
      expect(typeof result.current.setLanguage).toBe('function')
      expect(typeof result.current.setSidebarCollapsed).toBe('function')
      expect(typeof result.current.toggleSidebar).toBe('function')
    })
  })

  describe('multiple preference changes', () => {
    it('handles multiple changes in sequence', () => {
      const { result } = renderHook(() => usePreferences(), {
        wrapper: createWrapper(store),
      })

      act(() => {
        result.current.setDisplayMode('dark')
        result.current.setLanguage('de')
        result.current.setSidebarCollapsed(true)
      })

      expect(result.current.displayMode).toBe('dark')
      expect(result.current.language).toBe('de')
      expect(result.current.sidebarCollapsed).toBe(true)
    })
  })
})
