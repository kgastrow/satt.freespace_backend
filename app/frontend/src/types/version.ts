/**
 * Version information type
 * Used for version checking and deployment tracking
 */
export interface VersionInfo {
  version: string
  commit_hash: string
  build_time: string
}
