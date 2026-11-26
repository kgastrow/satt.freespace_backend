import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { changelogApi } from './changelogApi'

/**
 * State for changelog feature
 */
export interface ChangelogState {
  /** Number of unread changelog entries */
  unreadCount: number
  /** Whether we've checked for unread entries since login */
  hasCheckedSinceLogin: boolean
}

const initialState: ChangelogState = {
  unreadCount: 0,
  hasCheckedSinceLogin: false,
}

const changelogSlice = createSlice({
  name: 'changelog',
  initialState,
  reducers: {
    setHasCheckedSinceLogin: (state, action: PayloadAction<boolean>) => {
      state.hasCheckedSinceLogin = action.payload
    },
    resetChangelog: () => initialState,
  },
  extraReducers: (builder) => {
    builder.addMatcher(
      changelogApi.endpoints.getUnreadChangelogCount.matchFulfilled,
      (state, action) => {
        state.unreadCount = action.payload.count
      }
    )
    builder.addMatcher(
      changelogApi.endpoints.markAllChangelogsViewed.matchFulfilled,
      (state) => {
        state.unreadCount = 0
      }
    )
  },
})

export const { setHasCheckedSinceLogin, resetChangelog } =
  changelogSlice.actions

export default changelogSlice.reducer
