# Frontend Developer Skill

Expert React frontend developer for AYZER Webapp platform.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19 | UI framework |
| TypeScript | 5.9 | Type safety |
| Vite | 7 | Build tool with HMR |
| Tailwind CSS | 4 | Utility-first styling |
| shadcn/ui | Latest | Component library (Radix UI primitives) |
| Redux Toolkit | 2 | State management |
| RTK Query | 2 | Server state & data fetching |
| React Hook Form | 7 | Form handling |
| Zod | 4 | Schema validation |
| React Router | 7 | Client-side routing |
| Vitest | 4 | Unit/integration testing |

## Before Starting

1. Read `ai_docs/frontend/baseline_context.md`
2. Read relevant specialized context (see Quick Reference)
3. JWT tokens contain `organization_id`; backend enforces tenant isolation

## Project Structure

```
frontend/src/
├── components/ui/     # shadcn/ui components
├── features/          # Feature modules (slices, API, components)
├── hooks/             # Custom React hooks
├── layouts/           # Layout components (use <Outlet />)
├── lib/               # Utilities (cn() helper)
├── pages/             # Route page components
├── store/             # Redux store configuration
├── test/              # Test utilities
├── router.tsx         # Route definitions
└── main.tsx           # App entry with providers
```

## Core Patterns

### Components

```tsx
interface UserCardProps {
  user: User
  onEdit?: (id: string) => void
  className?: string
}

export function UserCard({ user, onEdit, className }: UserCardProps) {
  return <Card className={cn('p-4', className)}>{/* content */}</Card>
}
```

**Rules**: Named exports (not default), TypeScript interfaces, support `className` prop.

### RTK Query

```tsx
// src/features/users/usersApi.ts
export const usersApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getUsers: builder.query<UsersListResponse, { limit?: number; offset?: number }>({
      query: ({ limit = 10, offset = 0 }) => `/users?limit=${limit}&offset=${offset}`,
      providesTags: ['User'],
    }),
    createUser: builder.mutation<User, CreateUserRequest>({
      query: (body) => ({ url: '/users', method: 'POST', body }),
      invalidatesTags: ['User'],
    }),
  }),
})

export const { useGetUsersQuery, useCreateUserMutation } = usersApi
```

**Usage**: `const { data, isLoading, error } = useGetUsersQuery()`. Never use useEffect + fetch.

### Forms (React Hook Form + Zod)

```tsx
const userSchema = z.object({
  email: z.string().email('Invalid email'),
  firstName: z.string().min(1, 'Required'),
})
type UserFormData = z.infer<typeof userSchema>

export function UserForm({ onSubmit }: { onSubmit: (data: UserFormData) => void }) {
  const form = useForm<UserFormData>({
    resolver: zodResolver(userSchema),
    defaultValues: { email: '', firstName: '' },
  })
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <FormField control={form.control} name="email" render={({ field }) => (
          <FormItem><FormLabel>Email</FormLabel><FormControl><Input {...field} /></FormControl><FormMessage /></FormItem>
        )} />
        <Button type="submit" disabled={form.formState.isSubmitting}>Save</Button>
      </form>
    </Form>
  )
}
```

### Routing

Add routes in `src/router.tsx`. Use `<AuthGuard>` wrapper for authenticated routes, `<PermissionGate>` for permission-based access. Use `<Outlet />` in layouts.

### Styling

```tsx
import { cn } from '@/lib/utils'

// Semantic colors: bg-background, bg-card, text-foreground, text-muted-foreground
// Actions: bg-primary, bg-destructive
// Conditionals:
<div className={cn('rounded-lg p-4', isActive && 'bg-accent', className)}>
```

### Testing

```tsx
import { render, screen, waitFor } from '@/test/utils'
import userEvent from '@testing-library/user-event'

it('submits form', async () => {
  const user = userEvent.setup()
  const onSubmit = vi.fn()
  render(<UserForm onSubmit={onSubmit} />)

  await user.type(screen.getByLabelText(/email/i), 'test@example.com')
  await user.click(screen.getByRole('button', { name: /save/i }))

  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
})
```

## Common Tasks

| Task | Steps |
|------|-------|
| New page | 1. Create `src/pages/[Name].tsx` 2. Add route in `router.tsx` 3. Add test |
| New feature | 1. Create `src/features/[name]/` 2. Add `[name]Api.ts` 3. Add slice if needed 4. Add components |
| Add shadcn component | `npx shadcn@latest add [name]` |
| Add API endpoint | Define types → Add to feature Api file with tags → Export hooks |

### Auth & Permissions

```tsx
// Auth state
const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)
dispatch(setCredentials({ user, token }))
dispatch(logout())

// Permissions
const { canRead, canWrite, canDelete } = usePermission('api_keys')
<PermissionGate permission="users:write"><CreateUserButton /></PermissionGate>
```

### Notifications (Toast)

```tsx
import { toast } from '@/lib/toast'

// Basic usage (default icon based on type)
toast.success('User created')
toast.error('Failed to save')

// With category (custom icon)
toast.info('Welcome back', { category: 'auth' })      // Shield icon
toast.success('File uploaded', { category: 'file' })  // File icon
toast.info('New message', { category: 'notification' }) // Bell icon
```

Categories: `notification` (Bell), `auth` (Shield), `file` (File). Omit for default type icons.

### Error Handling

```tsx
import { toast } from '@/lib/toast'
const [createUser] = useCreateUserMutation()

try {
  await createUser(data).unwrap()
  toast.success('Created')
} catch (error: any) {
  error.data?.detail ? form.setError('root', { message: error.data.detail }) : toast.error('Something went wrong')
}
```

## Code Quality Checklist

- [ ] No `any` types, proper interfaces
- [ ] Named exports, props typed, `className` supported
- [ ] Zod schema with validation messages
- [ ] RTK Query hooks, loading/error states handled
- [ ] Semantic Tailwind classes, cn() for conditionals
- [ ] Tests for renders, interactions, edge cases

## Quick Reference

| Task | Context File |
|------|--------------|
| Components | `ai_docs/frontend/context/components.md` |
| State/API | `ai_docs/frontend/context/state.md` |
| Forms | `ai_docs/frontend/context/forms.md` |
| Routing | `ai_docs/frontend/context/routing.md` |
| Styling | `ai_docs/frontend/context/styling.md` |
| Testing | `ai_docs/frontend/context/testing.md` |

## Commands

```bash
npm run dev          # Dev server (localhost:5173)
npm run build        # Production build
npm test             # Tests (watch)
npm run lint         # Lint
npx shadcn@latest add [name]  # Add component
```

## Critical Rules

1. **Path aliases**: Import with `@/` prefix
2. **RTK Query only**: Never useEffect + fetch
3. **Colocate tests**: `Component.test.tsx` next to `Component.tsx`
4. **Feature folders**: Group in `src/features/[feature]/`
5. **Token storage**: sessionStorage (access), localStorage (refresh)
6. **Always handle**: loading and error states
