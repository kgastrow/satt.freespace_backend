import { Star } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StarRatingProps {
  value: number
  onChange: (value: number) => void
  max?: number
  disabled?: boolean
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-8 w-8',
}

export function StarRating({ value, onChange, max = 5, disabled = false, size = 'md' }: StarRatingProps) {
  return (
    <div className="flex gap-1">
      {Array.from({ length: max }, (_, i) => i + 1).map((rating) => (
        <button
          key={rating}
          type="button"
          onClick={() => !disabled && onChange(rating)}
          disabled={disabled}
          className={cn(
            'transition-colors',
            disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:scale-110',
          )}
          aria-label={`Rate ${rating} out of ${max}`}
        >
          <Star
            className={cn(
              sizeClasses[size],
              rating <= value ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300',
            )}
          />
        </button>
      ))}
    </div>
  )
}
