/**
 * SEC-F-010: Validate that no secrets are exposed via VITE_ environment variables
 *
 * All VITE_ prefixed variables are embedded in the client bundle and visible
 * to end users. This script runs before build to catch accidental secret exposure.
 */

import { readFileSync, existsSync } from 'fs'
import { resolve } from 'path'

const FORBIDDEN_PATTERNS = [
  { pattern: /secret/i, reason: 'secrets must not be client-exposed' },
  { pattern: /password/i, reason: 'passwords must not be client-exposed' },
  { pattern: /api[_-]?key/i, reason: 'API keys must not be client-exposed' },
  { pattern: /private[_-]?key/i, reason: 'private keys must not be client-exposed' },
  { pattern: /auth[_-]?token/i, reason: 'auth tokens must not be client-exposed' },
  { pattern: /access[_-]?token/i, reason: 'access tokens must not be client-exposed' },
  { pattern: /credential/i, reason: 'credentials must not be client-exposed' },
  { pattern: /db[_-]?(url|host|pass)/i, reason: 'database config must not be client-exposed' },
  { pattern: /redis[_-]?(url|host|pass)/i, reason: 'Redis config must not be client-exposed' },
  { pattern: /encryption/i, reason: 'encryption keys must not be client-exposed' },
  { pattern: /signing/i, reason: 'signing keys must not be client-exposed' },
]

/**
 * Parse a .env file and extract variable names (not values - we only need names)
 */
function parseEnvFile(filePath: string): string[] {
  if (!existsSync(filePath)) {
    return []
  }

  const content = readFileSync(filePath, 'utf-8')
  const varNames: string[] = []

  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    // Skip comments and empty lines
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }
    // Extract variable name (before the = sign)
    const match = trimmed.match(/^([A-Z_][A-Z0-9_]*)=/)
    if (match) {
      varNames.push(match[1])
    }
  }

  return varNames
}

function validateViteEnvVars(): void {
  // Collect VITE_ vars from both process.env and .env files
  const envVarsFromProcess = Object.keys(process.env).filter((key) => key.startsWith('VITE_'))

  // Also check .env files directly
  const rootDir = resolve(import.meta.dirname, '..')
  const envFiles = ['.env', '.env.local', '.env.development', '.env.production']
  const envVarsFromFiles = envFiles
    .flatMap((file) => parseEnvFile(resolve(rootDir, file)))
    .filter((key) => key.startsWith('VITE_'))

  // Combine and deduplicate
  const viteVars = [...new Set([...envVarsFromProcess, ...envVarsFromFiles])]

  const violations: string[] = []

  for (const varName of viteVars) {
    for (const { pattern, reason } of FORBIDDEN_PATTERNS) {
      if (pattern.test(varName)) {
        violations.push(`  - ${varName}: ${reason}`)
      }
    }
  }

  if (violations.length > 0) {
    console.error('\n❌ SEC-F-010: Potential secrets detected in VITE_ environment variables!\n')
    console.error('The following variables appear to contain sensitive data:')
    console.error(violations.join('\n'))
    console.error('\nVITE_ variables are embedded in the client bundle and visible to end users.')
    console.error('Move sensitive configuration to the backend and access via authenticated API.\n')
    process.exit(1)
  }

  console.log(`✓ SEC-F-010: Validated ${viteVars.length} VITE_ variables - no secrets detected`)
}

validateViteEnvVars()
