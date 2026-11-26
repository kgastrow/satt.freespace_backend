import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface AdminCardProps {
  icon: LucideIcon
  title: string
  description: string
  to: string
  className?: string
}

export function AdminCard({ icon: Icon, title, description, to, className }: AdminCardProps) {
  return (
    <Link to={to} className="block">
      <Card
        className={cn(
          'h-full transition-all hover:shadow-md hover:border-primary/50 cursor-pointer',
          className
        )}
      >
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            <CardTitle className="text-base">{title}</CardTitle>
          </div>
          <CardDescription className="mt-2">{description}</CardDescription>
        </CardHeader>
      </Card>
    </Link>
  )
}
