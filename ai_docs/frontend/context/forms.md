# React Hook Form + Zod Patterns

## Core Pattern

Define Zod schema -> infer TypeScript type -> use `useForm` with `zodResolver` -> use shadcn/ui Form components.

**Requirements:**
1. Use `<Form {...form}>` wrapper with shadcn/ui components
2. Use `FormField` component for fields (preferred over `register()` API)
3. All validation messages MUST use i18n translations
4. Edit forms: use `values` prop for server data sync
5. Create forms: call `form.reset()` after successful submission

```typescript
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'

// Schema factory with i18n (MANDATORY)
const createUserSchema = (t: (key: string) => string) => z.object({
  email: z.string().email(t('validation.invalidEmail')),
  firstName: z.string().min(1, t('validation.required')),
})
type UserFormData = z.infer<ReturnType<typeof createUserSchema>>

export function UserForm() {
  const { t } = useTranslation('users')
  const form = useForm<UserFormData>({
    resolver: zodResolver(createUserSchema(t)),
    defaultValues: { email: '', firstName: '' },
  })

  const onSubmit = async (data: UserFormData) => { /* API call */ }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField control={form.control} name="email" render={({ field }) => (
          <FormItem>
            <FormLabel>{t('email')}</FormLabel>
            <FormControl><Input type="email" {...field} /></FormControl>
            <FormMessage />
          </FormItem>
        )} />
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t('saving') : t('save')}
        </Button>
      </form>
    </Form>
  )
}
```

## Zod Validation Patterns

| Type | Pattern |
|------|---------|
| Required string | `z.string().min(1, t('required'))` |
| Email | `z.string().email(t('invalid'))` |
| URL | `z.string().url(t('invalidUrl'))` |
| Max length | `z.string().max(100, t('tooLong'))` |
| Regex | `z.string().regex(/pattern/, t('invalid'))` |
| Optional | `z.string().optional()` |
| Number | `z.coerce.number().min(0).int()` |
| Enum | `z.enum(['active', 'inactive'])` |
| Array | `z.array(z.string()).min(1, t('required'))` |

### Cross-Field Validation

```typescript
// Password confirmation
z.object({
  password: z.string().min(8),
  confirmPassword: z.string(),
}).refine(
  (data) => data.password === data.confirmPassword,
  { message: t('passwordsMustMatch'), path: ['confirmPassword'] }
)
```

## Form State & Methods

```typescript
const form = useForm<FormData>({...})

// State
const { isSubmitting, isValid, errors, isDirty } = form.formState

// Watch values
const email = form.watch('email')

// Set errors
form.setError('email', { message: 'Already exists' })
form.setError('root', { message: 'API error' })  // Global error

// Reset
form.reset()  // To defaults
form.reset({ email: 'new@example.com' })  // To values
```

## Edit Forms (Server Data Sync)

**Use `values` prop for edit forms.** This auto-syncs form state when server data changes.

```typescript
function EditUserForm({ userId }: { userId: string }) {
  const { data: user, isLoading } = useGetUserQuery(userId)

  const form = useForm<UserFormData>({
    resolver: zodResolver(userSchema),
    defaultValues: { email: '', firstName: '' },
    // Auto-sync with server data
    values: user ? { email: user.email, firstName: user.first_name } : undefined,
  })

  if (isLoading) return <Spinner />
  return <Form {...form}>...</Form>
}
```

**Gotcha - defaultValues vs values:**
```typescript
// WRONG - Only sets initial values, doesn't sync on prop changes
const form = useForm({
  defaultValues: { email: user?.email || '' },  // Won't update if user changes
})

// CORRECT - Auto-syncs when user data updates
const form = useForm({
  defaultValues: { email: '' },
  values: user ? { email: user.email } : undefined,
})
```

## RTK Query Integration

```typescript
const [createUser] = useCreateUserMutation()

const onSubmit = async (data: FormData) => {
  try {
    await createUser(data).unwrap()
    toast.success(t('createSuccess'))
    form.reset()  // REQUIRED for create forms
  } catch (error: unknown) {
    const apiError = error as { data?: { detail?: string } }
    apiError.data?.detail
      ? form.setError('root', { message: apiError.data.detail })
      : toast.error(t('common.error'))
  }
}
```

**Form Reset Rules:**
- **Create forms:** MUST call `form.reset()` after successful submission
- **Edit forms:** Do NOT call reset (the `values` prop auto-syncs)
- **Modal forms:** Reset optional if modal unmounts on close

## FormField vs register() API

**Prefer FormField** for consistency with shadcn/ui styling and accessibility:

```typescript
// PREFERRED - FormField with shadcn/ui
<FormField control={form.control} name="email" render={({ field }) => (
  <FormItem>
    <FormLabel>{t('email')}</FormLabel>
    <FormControl><Input {...field} /></FormControl>
    <FormMessage />  {/* Automatic error display */}
  </FormItem>
)} />

// ACCEPTABLE for simple inputs without Form wrapper (e.g., login forms)
<Input {...register('email')} />
{errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
```

**Why FormField is preferred:**
- Consistent shadcn/ui styling
- Automatic accessibility (aria attributes)
- Integrated error display via FormMessage
- FormLabel/FormDescription support

## Security Requirements

**Password fields:**
- Use `createPasswordSchema` from `@/lib/password-validation`
- Include `<PasswordRequirements>` component for visual feedback
- Use `autoComplete="new-password"` or `autoComplete="current-password"`

```typescript
import { createPasswordSchema } from '@/lib/password-validation'
import { PasswordRequirements } from '@/components/password'

const schema = z.object({
  password: createPasswordSchema(t),
})

<FormField name="password" render={({ field }) => (
  <FormItem>
    <FormLabel>{t('password')}</FormLabel>
    <FormControl>
      <Input type="password" autoComplete="new-password" {...field} />
    </FormControl>
    <PasswordRequirements control={form.control} name="password" />
    <FormMessage />
  </FormItem>
)} />
```

## Best Practices

| Practice | Why |
|----------|-----|
| Use Zod schemas | Type-safe validation |
| Use i18n in schemas | All validation messages must be translated |
| Use FormDescription | Explain field requirements |
| Map API errors to fields | Contextual feedback |
| Disable button on isSubmitting | Prevent double-submit |
| Reset create forms after success | Clear stale data |
| Use `values` for edit forms | Auto-sync with server |
