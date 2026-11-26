# Execute Wire Task

Wire a component to the new backend APIs.

## Arguments
- `$1` - ADW ID
- `$2` - Component path
- `$3` - API domain to wire to

## Context Files to Read
- `ai_docs/frontend/context/state.md`
- `ai_docs/backend/context/api.md`

## Instructions

### 1. Analyze Component

Read the component at `$2` and identify:
- Placeholder API hooks (TODO comments)
- Data fetching patterns
- Form submissions
- State that should come from API

### 2. Create RTK Query Hooks

If not exists, create API slice in `app/frontend/src/features/api/{domain}Api.ts`:

```typescript
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import type { {DomainName}, {DomainName}Create, {DomainName}Update } from '@/types/{domain}';

export const {domain}Api = createApi({
  reducerPath: '{domain}Api',
  baseQuery: fetchBaseQuery({
    baseUrl: '/api/v1',
    prepareHeaders: (headers) => {
      const token = localStorage.getItem('access_token');
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      return headers;
    },
  }),
  tagTypes: ['{DomainName}'],
  endpoints: (builder) => ({
    get{DomainName}s: builder.query<{DomainName}[], { skip?: number; limit?: number }>({
      query: ({ skip = 0, limit = 20 }) => `/{domain}s?skip=${skip}&limit=${limit}`,
      providesTags: ['{DomainName}'],
    }),
    get{DomainName}: builder.query<{DomainName}, string>({
      query: (id) => `/{domain}s/${id}`,
      providesTags: (result, error, id) => [{ type: '{DomainName}', id }],
    }),
    create{DomainName}: builder.mutation<{DomainName}, {DomainName}Create>({
      query: (body) => ({
        url: '/{domain}s',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['{DomainName}'],
    }),
    update{DomainName}: builder.mutation<{DomainName}, { id: string; data: {DomainName}Update }>({
      query: ({ id, data }) => ({
        url: `/{domain}s/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: '{DomainName}', id }],
    }),
    delete{DomainName}: builder.mutation<void, string>({
      query: (id) => ({
        url: `/{domain}s/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['{DomainName}'],
    }),
  }),
});

export const {
  useGet{DomainName}sQuery,
  useGet{DomainName}Query,
  useCreate{DomainName}Mutation,
  useUpdate{DomainName}Mutation,
  useDelete{DomainName}Mutation,
} = {domain}Api;
```

### 3. Register API in Store

Add to `app/frontend/src/store/index.ts`:

```typescript
import { {domain}Api } from '@/features/api/{domain}Api';

export const store = configureStore({
  reducer: {
    // ... existing reducers
    [{domain}Api.reducerPath]: {domain}Api.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(
      // ... existing middleware
      {domain}Api.middleware,
    ),
});
```

### 4. Update Component

Replace placeholder hooks with real RTK Query hooks:

```tsx
// Before
// TODO: Wire to actual API endpoint
const [data, setData] = useState([]);

// After
import { useGet{DomainName}sQuery } from '@/features/api/{domain}Api';

const { data, isLoading, error } = useGet{DomainName}sQuery({ skip: 0, limit: 20 });
```

### 5. Handle Loading and Error States

Ensure component handles:
- Loading state (`isLoading`)
- Error state (`error`)
- Empty state (no data)

```tsx
if (isLoading) {
  return <Spinner />;
}

if (error) {
  return <ErrorMessage error={error} />;
}

if (!data || data.length === 0) {
  return <EmptyState message={t('domain.empty')} />;
}
```

### 6. Wire Form Submissions

For forms, use mutations:

```tsx
import { useCreate{DomainName}Mutation } from '@/features/api/{domain}Api';

const [create{DomainName}, { isLoading: isCreating }] = useCreate{DomainName}Mutation();

const handleSubmit = async (data: {DomainName}Create) => {
  try {
    await create{DomainName}(data).unwrap();
    toast.success(t('domain.created'));
    navigate('/{domain}s');
  } catch (error) {
    toast.error(t('domain.createError'));
  }
};
```

## Output

Report:
1. API slice created/updated
2. Store registered
3. Component updated with hooks
4. Loading/error states added

Example:
```
Created API: app/frontend/src/features/api/postApi.ts
Hooks: useGetPostsQuery, useGetPostQuery, useCreatePostMutation, useUpdatePostMutation, useDeletePostMutation

Updated: app/frontend/src/components/features/PostList.tsx
- Replaced placeholder with useGetPostsQuery
- Added loading spinner
- Added error handling
- Added empty state

Updated: app/frontend/src/components/features/PostForm.tsx
- Wired to useCreatePostMutation
- Added form submission handling
- Added success/error toasts
```

## Validation

- API slice exports all CRUD hooks
- Store includes the API reducer and middleware
- Component uses actual RTK Query hooks (no placeholders)
- Loading and error states are handled
- TypeScript compiles without errors

$ARGUMENTS
