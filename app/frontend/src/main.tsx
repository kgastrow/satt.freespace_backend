import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import { RouterProvider } from 'react-router-dom'
import { ThemeProvider } from 'next-themes'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { UpdateBanner } from '@/components/UpdateBanner'
import { InstallBanner } from '@/components/InstallBanner'
import { PreferencesSync } from '@/features/preferences'
import { store } from '@/store'
import { router } from '@/router'
import './i18n'
import './registerSW'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <Provider store={store}>
          <PreferencesSync>
            <UpdateBanner />
            <InstallBanner />
            <RouterProvider router={router} />
          </PreferencesSync>
        </Provider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
)
