import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Allow exporting non-components from component files
      // Required for shadcn/ui pattern (exports variants, hooks alongside components)
      // Also allows HOCs like withAuthGuard
      'react-refresh/only-export-components': [
        'warn',
        {
          allowConstantExport: true,
          allowExportNames: [
            'buttonVariants',
            'useFormField',
            'Form',
            'FormField',
            'withAuthGuard',
          ],
        },
      ],
      // SEC-F-010: Warn when accessing VITE_ env vars with suspicious names
      // VITE_ variables are embedded in client bundle and visible to end users
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "MemberExpression[object.object.name='import'][object.property.name='meta'] > MemberExpression[object.property.name='env'][property.name=/^VITE_.*(SECRET|KEY|PASSWORD|TOKEN|CREDENTIAL|PRIVATE)/i]",
          message:
            'SEC-F-010: Suspected secret in VITE_ variable. VITE_ variables are exposed in the client bundle. Move secrets to backend.',
        },
      ],
    },
  },
  // Disable react-refresh for test utilities
  {
    files: ['src/test/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
