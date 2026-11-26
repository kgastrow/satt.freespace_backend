import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FileSearch, ArrowLeft, Search, X } from 'lucide-react'
import {
  useGetSubmissionsQuery,
  useGetActiveUserTypesQuery,
} from '@/store/api/onboardingApi'
import { SubmissionListItem } from '@/features/onboarding/SubmissionListItem'
import {
  SubmissionDetailPanel,
  SubmissionDetailSheet,
} from '@/features/onboarding/SubmissionDetailPanel'
import { useIsMobile } from '@/hooks/use-mobile'
import { useDebounce } from '@/hooks/use-debounce'

type StatusFilter = 'pending_review' | 'change_requested' | 'approved' | 'rejected'

function ListSkeleton() {
  return (
    <div className="space-y-0">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="p-4 border-b">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-16" />
          </div>
          <Skeleton className="h-3 w-24 mt-2" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ message, description }: { message: string; description: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-8">
      <FileSearch className="h-12 w-12 text-muted-foreground mb-4" />
      <h3 className="font-medium text-lg">{message}</h3>
      <p className="text-sm text-muted-foreground mt-1">{description}</p>
    </div>
  )
}

function SelectPlaceholder({
  title,
  description,
  keyboardHint,
}: {
  title: string
  description: string
  keyboardHint: string
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-8 border rounded-lg bg-muted/30">
      <FileSearch className="h-12 w-12 text-muted-foreground mb-4" />
      <h3 className="font-medium text-lg">{title}</h3>
      <p className="text-sm text-muted-foreground mt-1">{description}</p>
      <div className="mt-4 text-xs text-muted-foreground">
        <kbd className="px-2 py-1 bg-muted rounded text-xs">↑</kbd>
        <kbd className="px-2 py-1 bg-muted rounded text-xs ml-1">↓</kbd>
        <span className="ml-2">{keyboardHint}</span>
      </div>
    </div>
  )
}

export function OnboardingReviewPage() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  // Filter state
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending_review')
  const [searchInput, setSearchInput] = useState('')
  const [userTypeFilter, setUserTypeFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<string | null>(null)
  const pageSize = 20

  // Debounce search input
  const debouncedSearch = useDebounce(searchInput, 300)

  // Handler functions that reset page and selection when filters change
  const handleStatusFilterChange = useCallback((value: StatusFilter) => {
    setStatusFilter(value)
    setPage(1)
    setSelectedSubmissionId(null)
  }, [])

  const handleUserTypeFilterChange = useCallback((value: string) => {
    setUserTypeFilter(value)
    setPage(1)
    setSelectedSubmissionId(null)
  }, [])

  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value)
    setPage(1)
    setSelectedSubmissionId(null)
  }, [])

  // Fetch user types for filter dropdown
  const { data: userTypes } = useGetActiveUserTypesQuery()

  // Fetch submissions with filters
  const { data, isLoading } = useGetSubmissionsQuery({
    status: statusFilter,
    search: debouncedSearch || undefined,
    user_type_id: userTypeFilter === 'all' ? undefined : userTypeFilter,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const submissions = useMemo(() => data?.items || [], [data?.items])
  const totalPages = Math.ceil((data?.total || 0) / pageSize)

  // Find current index for navigation
  const currentIndex = submissions.findIndex((s) => s.id === selectedSubmissionId)
  const canNavigatePrev = currentIndex > 0
  const canNavigateNext = currentIndex >= 0 && currentIndex < submissions.length - 1

  const handleNavigatePrev = useCallback(() => {
    if (currentIndex > 0) {
      setSelectedSubmissionId(submissions[currentIndex - 1].id)
    }
  }, [currentIndex, submissions])

  const handleNavigateNext = useCallback(() => {
    if (currentIndex >= 0 && currentIndex < submissions.length - 1) {
      setSelectedSubmissionId(submissions[currentIndex + 1].id)
    }
  }, [currentIndex, submissions])

  const handleClose = useCallback(() => {
    setSelectedSubmissionId(null)
  }, [])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't handle if user is typing in an input/textarea
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      switch (e.key) {
        case 'ArrowDown':
        case 'j':
          e.preventDefault()
          if (selectedSubmissionId === null && submissions.length > 0) {
            setSelectedSubmissionId(submissions[0].id)
          } else {
            handleNavigateNext()
          }
          break
        case 'ArrowUp':
        case 'k':
          e.preventDefault()
          if (selectedSubmissionId === null && submissions.length > 0) {
            setSelectedSubmissionId(submissions[submissions.length - 1].id)
          } else {
            handleNavigatePrev()
          }
          break
        case 'Escape':
          e.preventDefault()
          handleClose()
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [
    selectedSubmissionId,
    submissions,
    handleNavigateNext,
    handleNavigatePrev,
    handleClose,
  ])

  const paginationElement =
    totalPages <= 1 ? null : (
      <div className="flex items-center justify-between p-3 border-t bg-background">
        <span className="text-xs text-muted-foreground">
          {t('onboardingReview.pagination.showing', {
            start: (page - 1) * pageSize + 1,
            end: Math.min(page * pageSize, data?.total || 0),
            total: data?.total || 0,
          })}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            {t('onboardingReview.pagination.previous')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            {t('onboardingReview.pagination.next')}
          </Button>
        </div>
      </div>
    )

  const headerElement = (
    <div className="flex items-center gap-4 mb-4">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/admin')}
        className="gap-2"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('onboardingReview.backToAdmin')}
      </Button>
      <div className="flex-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          {t('onboardingReview.pageTitle')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('onboardingReview.pageDescription')}
        </p>
      </div>
    </div>
  )

  const filtersElement = (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Search Input */}
      <div className="relative flex-1 min-w-[200px] max-w-[300px]">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={t('onboardingReview.search.placeholder')}
          value={searchInput}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="pl-9 pr-8 h-9"
        />
        {searchInput && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
            onClick={() => handleSearchChange('')}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* User Type Filter */}
      <Select value={userTypeFilter} onValueChange={handleUserTypeFilterChange}>
        <SelectTrigger className="w-[180px] h-9">
          <SelectValue placeholder={t('onboardingReview.filter.allUserTypes')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t('onboardingReview.filter.allUserTypes')}</SelectItem>
          {userTypes?.map((userType) => (
            <SelectItem key={userType.id} value={userType.id}>
              {userType.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  const statusLabel = {
    pending_review: t('onboardingReview.tabs.pending'),
    change_requested: t('onboardingReview.tabs.changeRequested'),
    approved: t('onboardingReview.tabs.approved'),
    rejected: t('onboardingReview.tabs.rejected'),
  }

  // Mobile view uses Sheet for detail
  if (isMobile) {
    return (
      <div className="space-y-4">
        {headerElement}
        {filtersElement}

        <div className="border rounded-lg">
          {/* Tabs */}
          <div className="p-2 border-b">
            <Tabs value={statusFilter} onValueChange={(v) => handleStatusFilterChange(v as StatusFilter)}>
              <TabsList className="w-full">
                <TabsTrigger value="pending_review" className="flex-1">
                  {t('onboardingReview.tabs.pending')}
                </TabsTrigger>
                <TabsTrigger value="change_requested" className="flex-1">
                  {t('onboardingReview.tabs.changeRequested')}
                </TabsTrigger>
                <TabsTrigger value="approved" className="flex-1">
                  {t('onboardingReview.tabs.approved')}
                </TabsTrigger>
                <TabsTrigger value="rejected" className="flex-1">
                  {t('onboardingReview.tabs.rejected')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <div className="p-2 border-b bg-muted/30">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{statusLabel[statusFilter]}</span>
              <Badge variant="secondary">{data?.total || 0}</Badge>
            </div>
          </div>

          {isLoading ? (
            <ListSkeleton />
          ) : submissions.length === 0 ? (
            <EmptyState
              message={t('onboardingReview.emptyMessage')}
              description={t('onboardingReview.emptyDescription')}
            />
          ) : (
            <>
              <ScrollArea className="h-[calc(100vh-340px)]">
                {submissions.map((submission) => (
                  <SubmissionListItem
                    key={submission.id}
                    submission={submission}
                    isSelected={selectedSubmissionId === submission.id}
                    onClick={() => setSelectedSubmissionId(submission.id)}
                  />
                ))}
              </ScrollArea>
              {paginationElement}
            </>
          )}
        </div>

        <SubmissionDetailSheet
          userUserTypeId={selectedSubmissionId}
          onClose={handleClose}
          onNavigatePrev={handleNavigatePrev}
          onNavigateNext={handleNavigateNext}
          canNavigatePrev={canNavigatePrev}
          canNavigateNext={canNavigateNext}
        />
      </div>
    )
  }

  // Desktop split view
  return (
    <div className="space-y-4">
      {headerElement}

      <div className="flex gap-6 h-[calc(100vh-140px)]">
        {/* Master List */}
        <div className="w-2/5 min-w-[320px] max-w-[480px] flex flex-col border rounded-lg">
          {/* Tabs */}
          <div className="p-2 border-b flex-shrink-0">
            <Tabs value={statusFilter} onValueChange={(v) => handleStatusFilterChange(v as StatusFilter)}>
              <TabsList className="w-full">
                <TabsTrigger value="pending_review" className="flex-1">
                  {t('onboardingReview.tabs.pending')}
                </TabsTrigger>
                <TabsTrigger value="change_requested" className="flex-1">
                  {t('onboardingReview.tabs.changeRequested')}
                </TabsTrigger>
                <TabsTrigger value="approved" className="flex-1">
                  {t('onboardingReview.tabs.approved')}
                </TabsTrigger>
                <TabsTrigger value="rejected" className="flex-1">
                  {t('onboardingReview.tabs.rejected')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Filters */}
          <div className="p-2 border-b flex-shrink-0 space-y-2">
            {filtersElement}
          </div>

          {/* List header with count */}
          <div className="p-2 border-b bg-muted/30 flex-shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{statusLabel[statusFilter]}</span>
              <Badge variant="secondary">{data?.total || 0}</Badge>
            </div>
          </div>

          {isLoading ? (
            <ListSkeleton />
          ) : submissions.length === 0 ? (
            <EmptyState
              message={t('onboardingReview.emptyMessage')}
              description={t('onboardingReview.emptyDescription')}
            />
          ) : (
            <>
              <ScrollArea className="flex-1">
                {submissions.map((submission) => (
                  <SubmissionListItem
                    key={submission.id}
                    submission={submission}
                    isSelected={selectedSubmissionId === submission.id}
                    onClick={() => setSelectedSubmissionId(submission.id)}
                  />
                ))}
              </ScrollArea>
              {paginationElement}
            </>
          )}
        </div>

        {/* Detail Panel */}
        <div className="flex-1 min-w-0">
          {selectedSubmissionId ? (
            <SubmissionDetailPanel
              userUserTypeId={selectedSubmissionId}
              onClose={handleClose}
              onNavigatePrev={handleNavigatePrev}
              onNavigateNext={handleNavigateNext}
              canNavigatePrev={canNavigatePrev}
              canNavigateNext={canNavigateNext}
            />
          ) : (
            <SelectPlaceholder
              title={t('onboardingReview.list.selectToReview')}
              description={t('onboardingReview.list.selectToReviewDescription')}
              keyboardHint={t('onboardingReview.keyboard.navigate')}
            />
          )}
        </div>
      </div>
    </div>
  )
}
