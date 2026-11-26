import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { TableSkeleton } from '@/components/skeletons'
import {
  useGetOrganizationQuery,
  useGetOrganizationMembersQuery,
  useRemoveOrganizationMemberMutation,
  type OrganizationMember,
} from '@/features/organizations/organizationsApi'

export function OrganizationMembersPage() {
  const { id } = useParams<{ id: string }>()
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data: organization, isLoading: isLoadingOrg } = useGetOrganizationQuery(id!)
  const { data: membersData, isLoading: isLoadingMembers } =
    useGetOrganizationMembersQuery({
      id: id!,
      limit: pageSize,
      offset: (page - 1) * pageSize,
    })

  const [removeMember, { isLoading: isRemoving }] = useRemoveOrganizationMemberMutation()
  const [removingMember, setRemovingMember] = useState<OrganizationMember | null>(null)

  const handleRemove = async () => {
    if (!removingMember || !id) return
    try {
      await removeMember({ orgId: id, userId: removingMember.id }).unwrap()
      toast.success('Member removed successfully')
      setRemovingMember(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to remove member')
    }
  }

  const columns: Column<OrganizationMember>[] = [
    {
      key: 'email',
      header: 'Email',
      cell: (member) => member.email,
    },
    {
      key: 'roles',
      header: 'Roles',
      cell: (member) => (
        <div className="flex flex-wrap gap-1">
          {member.is_admin && <Badge>Admin</Badge>}
        </div>
      ),
    },
    {
      key: 'joined',
      header: 'Joined',
      cell: (member) => member.created_time ? new Date(member.created_time).toLocaleDateString() : '-',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (member) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() => setRemovingMember(member)}
              className="text-destructive"
            >
              Remove from Organization
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  if (isLoadingOrg) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-64 mb-2" />
          <Skeleton className="h-4 w-96 mb-6" />
        </div>
        <TableSkeleton columns={columns} rows={pageSize} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/platform-admin/organizations" className="hover:underline">
          Organizations
        </Link>
        <span>/</span>
        <span>{organization?.name}</span>
        <span>/</span>
        <span>Members</span>
      </div>

      <PageHeader
        title={`${organization?.name || 'Organization'} Members`}
        description="View and manage organization members"
      >
        <Button asChild variant="outline">
          <Link to="/platform-admin/organizations">Back to Organizations</Link>
        </Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={membersData?.items || []}
        isLoading={isLoadingMembers}
        emptyMessage="No members found"
        pagination={{
          page,
          pageSize,
          total: membersData?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Remove Member Confirmation */}
      <ConfirmDialog
        open={!!removingMember}
        onOpenChange={() => setRemovingMember(null)}
        title="Remove Member"
        description={`Are you sure you want to remove ${removingMember?.email} from this organization? They will lose access to all organization resources.`}
        confirmLabel="Remove"
        onConfirm={handleRemove}
        isLoading={isRemoving}
        variant="destructive"
      />
    </div>
  )
}
