# Redux Toolkit + RTK Query Patterns

## Overview

Redux Toolkit for state management, RTK Query for data fetching with automatic caching and invalidation.

## Store Structure

```
app/frontend/src/store/
├── index.ts          # Store configuration with all reducers
├── api.ts            # Base RTK Query API with token refresh
├── hooks.ts          # Typed useDispatch/useSelector
├── authMiddleware.ts # Handles logout side effects (toast, redirect)
└── api/              # Feature-specific API endpoints
```

**Always use typed hooks:**
```typescript
import { useAppDispatch, useAppSelector } from '@/store/hooks'
const dispatch = useAppDispatch()
const user = useAppSelector((state) => state.auth.user)
```

## RTK Query API Pattern

```typescript
// src/features/users/usersApi.ts
import { api } from '@/store/api'

export const usersApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // GET - LIST tag for create/delete invalidation
    getUsers: builder.query<User[], void>({
      query: () => '/users',
      providesTags: (result) =>
        result
          ? [...result.map(({ id }) => ({ type: 'User' as const, id })), { type: 'User', id: 'LIST' }]
          : [{ type: 'User', id: 'LIST' }],
    }),

    // GET by ID
    getUser: builder.query<User, string>({
      query: (id) => `/users/${id}`,
      providesTags: (result, error, id) => [{ type: 'User', id }],
    }),

    // POST - invalidate LIST
    createUser: builder.mutation<User, CreateUserRequest>({
      query: (body) => ({ url: '/users', method: 'POST', body }),
      invalidatesTags: [{ type: 'User', id: 'LIST' }],
    }),

    // PUT - invalidate specific item
    updateUser: builder.mutation<User, { id: string; data: Partial<User> }>({
      query: ({ id, data }) => ({ url: `/users/${id}`, method: 'PUT', body: data }),
      invalidatesTags: (result, error, { id }) => [{ type: 'User', id }],
    }),

    // DELETE - invalidate item + LIST
    deleteUser: builder.mutation<void, string>({
      query: (id) => ({ url: `/users/${id}`, method: 'DELETE' }),
      invalidatesTags: (result, error, id) => [{ type: 'User', id }, { type: 'User', id: 'LIST' }],
    }),
  }),
})

export const { useGetUsersQuery, useGetUserQuery, useCreateUserMutation, useUpdateUserMutation, useDeleteUserMutation } = usersApi
```

## Using Hooks

### Query
```typescript
const { data: users, isLoading, error } = useGetUsersQuery()
const { data: user } = useGetUserQuery(userId, { skip: !userId })  // Conditional
```

### Mutation
```typescript
const [createUser, { isLoading }] = useCreateUserMutation()

const handleSubmit = async (data: CreateUserRequest) => {
  try {
    await createUser(data).unwrap()  // Use unwrap() for try/catch
    toast.success('User created')
  } catch (error) {
    toast.error('Failed to create user')
  }
}
```

## Client-Side State (Slices)

For non-API state:

```typescript
// src/features/ui/uiSlice.ts
import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

const uiSlice = createSlice({
  name: 'ui',
  initialState: { sidebarOpen: true },
  reducers: {
    toggleSidebar: (state) => { state.sidebarOpen = !state.sidebarOpen },
  },
})

export const { toggleSidebar } = uiSlice.actions
export default uiSlice.reducer
```

## Authentication

### Auth State
The auth state uses `token` field for access token. Refresh token is stored in httpOnly cookie (server-side, not in Redux).

```typescript
// Auth state shape
interface AuthState {
  user: User | null
  token: string | null  // Access token
  isAuthenticated: boolean
  isLoading: boolean
  twoFactor: { required: boolean; token: string | null }
  // ... SSO state
}
```

### Auth Actions
```typescript
import { setCredentials, logout } from '@/features/auth/authSlice'
dispatch(setCredentials({ token }))  // After login
dispatch(logout())  // Logout
```

### Auto Token in Requests
```typescript
// src/store/api.ts - prepareHeaders adds token automatically
const token = (getState() as RootState).auth.token
if (token) headers.set('Authorization', `Bearer ${token}`)
```

### Token Refresh (Security-Critical)

Base API handles 401 automatically using httpOnly cookie:
1. On 401, attempt refresh via `POST /auth/refresh` (cookie sent automatically)
2. Success: dispatch `updateToken`, retry original request
3. Failure: dispatch `logout({ reason: 'session-expired' })`

```typescript
// src/store/api.ts - simplified
const baseQueryWithReauth: BaseQueryFn = async (args, api, extraOptions) => {
  let result = await baseQuery(args, api, extraOptions)
  if (result.error?.status === 401 && !isRefreshRequest) {
    // Refresh token is in httpOnly cookie - no body needed
    const refreshResult = await baseQuery({ url: '/auth/refresh', method: 'POST' }, api, extraOptions)
    if (refreshResult.data) {
      api.dispatch({ type: 'auth/updateToken', payload: data.access_token })
      result = await baseQuery(args, api, extraOptions)  // Retry
    } else {
      api.dispatch({ type: 'auth/logout', payload: { reason: 'session-expired' } })
    }
  }
  return result
}
```

### Auth Middleware (Logout Handling)

The `authMiddleware` handles logout side effects based on reason:
- `session-expired`: Shows toast, redirects to `/login`
- `impersonation-ended`: Shows warning toast, redirects to `/login`

## Using extraReducers

Sync slice state with RTK Query responses:

```typescript
const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: { /* ... */ },
  extraReducers: (builder) => {
    builder.addMatcher(authApi.endpoints.login.matchFulfilled, (state, action) => {
      state.token = action.payload.access_token
      state.isAuthenticated = true
    })
    builder.addMatcher(authApi.endpoints.getCurrentUser.matchFulfilled, (state, action) => {
      state.user = action.payload
    })
  },
})
```

## Per-Item Loading States in Lists

RTK Query's `isLoading` is shared across all mutation calls. For inline list actions, track the specific item ID.

> **Note:** Most admin pages use modal dialogs for mutations, avoiding this issue. Use per-item loading only for inline list actions.

```typescript
// Track specific item ID for inline actions
const [deleteItem] = useDeleteItemMutation()
const [deletingId, setDeletingId] = useState<string | null>(null)

const handleDelete = async (id: string) => {
  setDeletingId(id)
  try {
    await deleteItem(id).unwrap()
  } finally {
    setDeletingId(null)
  }
}
```

## Memoized Selectors

Use `createSelector` from RTK for derived state. Selectors are in feature-specific `*Selectors.ts` files.

```typescript
// src/features/auth/authSelectors.ts
import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '@/store'

const selectAuthState = (state: RootState) => state.auth

export const selectUser = createSelector(selectAuthState, (auth) => auth.user)
export const selectUserPermissions = createSelector(selectUser, (user) => user?.permissions ?? [])

// Parameterized selector
export const selectHasPermission = createSelector(
  [selectUserPermissions, (_state: RootState, permission: string) => permission],
  (permissions, permission) => permissions.includes(permission)
)
```

### Existing Selector Files

| File | Purpose |
|------|---------|
| `features/auth/authSelectors.ts` | User, permissions, authentication state |
| `features/websocket/websocketSelectors.ts` | Connection status, messages |
| `features/impersonation/impersonationSelectors.ts` | Impersonation state |

### When to Use createSelector

| Scenario | Use createSelector? |
|----------|---------------------|
| Direct state access (`state.auth.user`) | No |
| Derived/computed values | Yes |
| Filtering/mapping arrays | Yes |
| Multiple state dependencies | Yes |

## Best Practices

| Practice | Why |
|----------|-----|
| Use RTK Query for API calls | Don't use useEffect + fetch |
| Add tag types | Enable automatic cache invalidation |
| Use `unwrap()` | Get actual response in try/catch |
| Use LIST tag pattern | For proper list invalidation on create/delete |
| Use extraReducers | To sync slice state with API responses |
| Feature-based organization | Keep API endpoints with their feature |

## Query DSL for List Endpoints

Utilities in `src/lib/query-types.ts` and `src/lib/query-builder.ts` for building standardized query strings.

**Types**:
```typescript
interface ListResponse<T> { items: T[]; total: number; limit: number; offset: number }
interface FilterSpec { field: string; operator?: FilterOperator; value: string | string[] | boolean }
```

**Query Builder**:
```typescript
import { buildQueryString, createQueryBuilder } from '@/lib/query-builder'

// Object-based
buildQueryString({
  filters: [{ field: 'status', value: 'pending' }],
  sort: 'created_at:desc',
  pagination: { limit: 20, offset: 0 }
})

// Fluent API
createQueryBuilder()
  .filter('status', 'pending')
  .sort('created_at', 'desc')
  .paginate(20, 0)
  .build()
```

**RTK Query pattern**:
```typescript
getFilteredItems: builder.query<ListResponse<Item>, FilterParams>({
  query: (params) => {
    const queryString = buildQueryString({
      filters: [{ field: 'status', value: params.status }],
      pagination: { limit: params.limit, offset: params.offset },
    })
    return `/items?${queryString}`
  },
})
```
