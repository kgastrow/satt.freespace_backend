/**
 * Impersonation feature exports
 */

export { default as impersonationReducer } from './impersonationSlice'
export { clearImpersonation } from './impersonationSlice'
export {
  impersonationApi,
  useStartImpersonationMutation,
  useEndImpersonationMutation,
  useGetCurrentSessionQuery,
  useLazyGetCurrentSessionQuery,
  useGetImpersonationHistoryQuery,
} from './impersonationApi'
