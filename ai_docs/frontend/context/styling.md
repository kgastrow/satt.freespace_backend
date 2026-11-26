# Tailwind CSS Styling Patterns

Tailwind CSS v4 with shadcn/ui. Variables in `src/index.css`.

## Theme Variables

| Core | Status |
|------|--------|
| `background`, `foreground` | `success`, `success-foreground` |
| `card`, `card-foreground` | `warning`, `warning-foreground` |
| `primary`, `primary-foreground` | `info`, `info-foreground` |
| `secondary`, `secondary-foreground` | `destructive`, `destructive-foreground` |
| `muted`, `muted-foreground` | |
| `accent`, `accent-foreground` | |
| `border`, `input`, `ring` | |

Usage: `bg-primary`, `text-muted-foreground`, `border-border`

**Dark mode**: `.dark` class on parent. Variables auto-switch.

## shadcn/ui Components

Always use shadcn/ui components instead of raw elements:

```tsx
// Buttons - use variant prop
<Button variant="default">Primary</Button>
<Button variant="secondary">Secondary</Button>
<Button variant="outline">Outline</Button>
<Button variant="destructive">Delete</Button>
<Button variant="warning">Warning</Button>
<Button variant="ghost">Ghost</Button>
<Button variant="link">Link</Button>

// Button sizes
<Button size="sm" />
<Button size="default" />
<Button size="lg" />
<Button size="icon" />

// Cards
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content</CardContent>
  <CardFooter>Footer</CardFooter>
</Card>
```

## Common Patterns

```tsx
// Layout
<div className="min-h-screen bg-background">
<div className="container max-w-4xl mx-auto py-8 px-4">
<div className="flex items-center justify-center">
<div className="grid grid-cols-1 md:grid-cols-2 gap-4">

// Typography
<h1 className="text-3xl font-bold tracking-tight">
<p className="text-sm text-muted-foreground">

// Form spacing
<form className="space-y-4">
  <div className="space-y-2">
    <Label>Label</Label>
    <Input />
  </div>
</form>
```

## Responsive (Mobile-First)

```tsx
<div className="flex flex-col md:flex-row">
<div className="hidden md:block">
<div className="block md:hidden">
<div className="p-4 md:p-6">
```

## cn() Helper

```typescript
import { cn } from '@/lib/utils'

<div className={cn(
  'rounded-lg p-4',
  isActive && 'bg-accent',
  className
)}>
```

## Adding Custom Colors

In `src/index.css`:
```css
@theme inline {
  --color-brand: oklch(0.6 0.2 250);
}
```
Then use: `bg-brand`

## Best Practices

1. **Use shadcn/ui components** - Never raw buttons/inputs
2. **Semantic colors** - `bg-primary` not `bg-blue-500`
3. **Mobile-first** - Start mobile, add `md:` breakpoints
4. **Use cn()** - For conditional class merging
5. **Test dark mode** - Ensure both themes work
