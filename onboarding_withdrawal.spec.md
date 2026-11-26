# Self-Service Onboarding Withdrawal — Change Spec

Lets a user back out of an in-flight `UserUserType` onboarding (in_progress, pending_review, change_requested) so they can choose a different profile type or restart. Approved/rejected/expired/pending submissions are not self-withdrawable. Withdrawal is split from rejection: a withdrawing user can re-select the same user type cleanly because the partial unique index on `user_user_type` only constrains rows where `deleted_time IS NULL`.

Stack: FastAPI + SQLAlchemy 2.0 backend, React 19 + RTK Query + shadcn/ui frontend.

---

## 1. Backend — `app/backend/src/services/onboarding_notifications.py`

Add a new method on `OnboardingNotificationService`. Insert directly above the existing `_get_org_admin_user_ids` method.

```python
    async def send_user_withdrew_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
        user_type_name: str,
        prior_status: str,
    ) -> None:
        """
        Send notification to org admins that a user has withdrawn from onboarding.

        Used to clear stale items from the admin review queue when a user backs
        out of an in-flight submission.
        """
        try:
            user = await self._get_user(session, user_id, organization_id)
            user_name = ""
            if user:
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not user_name:
                    user_name = user.email

            admin_user_ids = await self._get_org_admin_user_ids(
                session, organization_id
            )

            for admin_user_id in admin_user_ids:
                await self.broadcaster.send_to_user(
                    admin_user_id,
                    "onboarding_withdrawn",
                    {
                        "message": f"{user_name} withdrew from {user_type_name} onboarding",
                        "user_id": user_id,
                        "user_user_type_id": user_user_type_id,
                        "prior_status": prior_status,
                    },
                )

            logger.info(
                f"Sent withdrawal notification to {len(admin_user_ids)} admins "
                f"in org {organization_id} for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send withdrawal notification for onboarding {user_user_type_id}: {e}"
            )
```

---

## 2. Backend — `app/backend/src/api/onboarding.py`

### 2a. New import

Add to the existing service imports near the top of the file:

```python
from src.services.audit import audit_service, get_client_ip, get_user_agent
```

### 2b. New endpoint

Insert this block immediately above the existing `@router.get("/submissions/{user_user_type_id}/comments", ...)` endpoint:

```python
_WITHDRAWABLE_STATUSES = {
    OnboardingStatus.IN_PROGRESS,
    OnboardingStatus.PENDING_REVIEW,
    OnboardingStatus.CHANGE_REQUESTED,
}


@router.delete("/submissions/{user_user_type_id}")
async def withdraw_onboarding(
    user_user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Withdraw the current user from an in-flight onboarding for a user type.

    Allowed only while the submission is still in motion (in_progress,
    pending_review, change_requested). Soft-deletes the UserUserType row,
    cascading to progress and review comments, and invalidates the user's
    permission cache. The user is then free to start a fresh onboarding for
    the same or a different user type.
    """
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    user_user_type = await user_user_type_crud.get_by_id(
        session, user_user_type_id, str(current_user.organization_id)
    )

    if not user_user_type:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if str(user_user_type.user_id) != str(current_user.id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only withdraw from your own onboarding submissions",
            detail_code="common.forbidden",
        )

    prior_status = user_user_type.onboarding_status
    if prior_status not in _WITHDRAWABLE_STATUSES:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot withdraw - onboarding status is '{prior_status.value}'",
            detail_code="common.validation_error",
        )

    from src.crud import user_type as user_type_crud

    user_type = await user_type_crud.get_by_id(
        session, str(user_user_type.user_type_id)
    )
    user_type_name = user_type.name if user_type else ""

    await user_user_type_crud.delete(
        session, user_user_type_id, str(current_user.organization_id)
    )

    await audit_service.log_delete(
        session=session,
        organization_id=str(current_user.organization_id),
        resource_type="UserUserType",
        resource_id=user_user_type_id,
        actor_id=str(current_user.id),
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
        resource_data={
            "user_type_id": str(user_user_type.user_type_id),
            "user_type_name": user_type_name,
            "prior_status": prior_status.value,
            "withdrawn_by": "user",
        },
    )

    if prior_status in (
        OnboardingStatus.PENDING_REVIEW,
        OnboardingStatus.CHANGE_REQUESTED,
    ):
        await onboarding_notification_service.send_user_withdrew_notification(
            session,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
            user_user_type_id=user_user_type_id,
            user_type_name=user_type_name,
            prior_status=prior_status.value,
        )

    return {
        "message": "Onboarding withdrawn",
        "user_user_type_id": user_user_type_id,
        "prior_status": prior_status.value,
    }
```

Notes:
- `user_user_type_crud.delete()` already soft-deletes (sets `deleted_time`) and invalidates the permission cache via `cache_service.invalidate_user_permissions`. No new CRUD code is needed.
- Cascading soft-delete of `UserOnboardingProgress` and `OnboardingReviewComment` is handled by the existing relationship `cascade="all, delete-orphan"` on `UserUserType`.
- Notification is suppressed for `IN_PROGRESS` withdrawals because nothing is in the admin review queue yet.
- The partial unique index `uq_user_user_type_active` in `app/backend/src/models/user_user_type.py` must carry both `postgresql_where=` and `sqlite_where=` clauses so the restart-same-user-type test passes under the SQLite test harness (Postgres is the source of truth in prod, but `sqlite_where` makes local tests match):

```python
    __table_args__ = (
        Index(
            "uq_user_user_type_active",
            "organization_id",
            "user_id",
            "user_type_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
            sqlite_where=text("deleted_time IS NULL"),
        ),
    )
```

---

## 3. Backend tests — `app/backend/tests/api_tests/test_onboarding_api.py`

Append at end of file:

```python
# ─────────────────────────────────────────────────────────────
# Withdraw Onboarding Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_withdraw_onboarding_requires_auth(client: AsyncClient):
    """Withdrawing requires authentication."""
    response = await client.delete(f"/api/v1/onboarding/submissions/{uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_withdraw_onboarding_feature_disabled(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_disabled,
):
    """Withdraw is blocked when the onboarding feature flag is off."""
    with mock_onboarding_disabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_withdraw_onboarding_not_found(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Withdrawing a non-existent submission returns 404."""
    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{uuid4()}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_withdraw_onboarding_in_progress_success(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """In-progress withdrawal soft-deletes the row and does not notify admins."""
    from src.models.user_user_type import UserUserType

    uut_id = str(test_user_user_type.id)

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{uut_id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["prior_status"] == "in_progress"
    mock_notify.assert_not_called()

    await async_session.refresh(test_user_user_type)
    fetched = await async_session.get(UserUserType, test_user_user_type.id)
    assert fetched is not None
    assert fetched.deleted_time is not None


@pytest.mark.asyncio
async def test_withdraw_onboarding_pending_review_notifies_admins(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Withdrawing while pending_review sends a notification to admins."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    assert response.json()["prior_status"] == "pending_review"
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_withdraw_onboarding_blocked_when_approved(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Approved onboarding cannot be self-withdrawn."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.APPROVED
    await async_session.commit()

    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_withdraw_onboarding_blocked_when_rejected(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Rejected onboarding cannot be self-withdrawn (terminal state)."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.REJECTED
    await async_session.commit()

    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cannot_withdraw_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
    mock_onboarding_enabled,
):
    """User cannot withdraw a submission belonging to another org."""
    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_withdraw_then_restart_same_user_type(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """After withdrawing, the user can start a fresh onboarding for the same user type."""
    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ):
        withdraw_resp = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )
        assert withdraw_resp.status_code == 200

        restart_resp = await client.post(
            f"/api/v1/onboarding/start/{test_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert restart_resp.status_code in [200, 201]
    data = restart_resp.json()
    assert data["user_user_type_id"] != str(test_user_user_type.id)
```

---

## 4. Frontend — `app/frontend/src/store/api/onboardingApi.ts`

### 4a. New mutation

Insert this endpoint inside `onboardingApi.injectEndpoints({ endpoints: (builder) => ({ ... }) })`, immediately before the existing `getMyReviewComments` query:

```typescript
    /**
     * DELETE /onboarding/submissions/{user_user_type_id} - User withdraws from in-flight onboarding
     */
    withdrawOnboarding: builder.mutation<
      { message: string; user_user_type_id: string; prior_status: string },
      string
    >({
      query: (userUserTypeId) => ({
        url: `/onboarding/submissions/${userUserTypeId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: 'STATUS' },
        { type: 'UserOnboarding', id: 'MY_USER_TYPES' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: 'PENDING_REVIEWS' },
        { type: 'UserOnboarding', id: userUserTypeId },
      ],
    }),
```

### 4b. New hook export

In the `export const { ... } = onboardingApi` block, add `useWithdrawOnboardingMutation` after `useResubmitForReviewMutation` and before `useGetMyReviewCommentsQuery`:

```typescript
  useResubmitForReviewMutation,
  useWithdrawOnboardingMutation,
  useGetMyReviewCommentsQuery,
```

---

## 5. Frontend i18n — `app/frontend/src/locales/en/onboarding.json`

### 5a. User-type context in the wizard header

In the `wizard` object, add `userTypeContext` directly below `title`:

```json
  "wizard": {
    "title": "Onboarding Progress",
    "userTypeContext": "Onboarding for {{userType}}",
    ...
```

### 5b. Withdraw dialog strings

In the same `wizard` object, add a `withdraw` block as a new sibling of `userTypeSelection`:

```json
    "withdraw": {
      "trigger": "Choose a different profile type",
      "title": "Withdraw from this onboarding?",
      "descriptionInProgress": "This will discard your progress on the {{userType}} onboarding. You can start again with this or a different profile type at any time.",
      "descriptionPendingReview": "Your {{userType}} onboarding is awaiting administrator review. Withdrawing will stop the review and discard your answers.",
      "descriptionChangeRequested": "Your {{userType}} onboarding has changes requested. Withdrawing will discard your answers and end the review thread.",
      "confirm": "Withdraw and start over",
      "cancel": "Keep going",
      "submitting": "Withdrawing...",
      "success": "Onboarding withdrawn",
      "error": "Failed to withdraw onboarding"
    }
```

Add the equivalent keys to every other locale file under `app/frontend/src/locales/<lang>/onboarding.json` (i18n is mandatory per `CLAUDE.md`). For `af` the `userTypeContext` reads `"Inskakeling vir {{userType}}"`.

---

## 6. Frontend shared component — `app/frontend/src/features/onboarding/WithdrawAction.tsx`

The withdraw confirmation is a standalone, reusable component so both the wizard and the dashboard progress card can embed it. Create the new file:

```typescript
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useWithdrawOnboardingMutation } from '@/store/api/onboardingApi'

export type WithdrawableStatus = 'in_progress' | 'pending_review' | 'change_requested'

interface WithdrawActionProps {
  userUserTypeId: string
  status: WithdrawableStatus
  userTypeName: string
  className?: string
}

export function WithdrawAction({
  userUserTypeId,
  status,
  userTypeName,
  className,
}: WithdrawActionProps) {
  const { t } = useTranslation('onboarding')
  const [withdraw, { isLoading }] = useWithdrawOnboardingMutation()

  const descriptionKey =
    status === 'pending_review'
      ? 'wizard.withdraw.descriptionPendingReview'
      : status === 'change_requested'
        ? 'wizard.withdraw.descriptionChangeRequested'
        : 'wizard.withdraw.descriptionInProgress'

  const handleConfirm = async () => {
    try {
      await withdraw(userUserTypeId).unwrap()
      toast.success(t('wizard.withdraw.success'))
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('wizard.withdraw.error'))
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="link"
          size="sm"
          className={
            className ??
            'h-auto p-0 text-muted-foreground hover:text-foreground'
          }
        >
          {t('wizard.withdraw.trigger')}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('wizard.withdraw.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t(descriptionKey, { userType: userTypeName })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>
            {t('wizard.withdraw.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {t('wizard.withdraw.submitting')}
              </>
            ) : (
              t('wizard.withdraw.confirm')
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
```

---

## 7. Frontend wizard — `app/frontend/src/features/onboarding/OnboardingWizard.tsx`

### 7a. Imports

Import the shared `WithdrawAction` alongside the existing RTK Query hooks (no `AlertDialog` or `useWithdrawOnboardingMutation` import is needed in the wizard file — both live in `WithdrawAction.tsx`):

```typescript
import {
  useGetOnboardingStatusQuery,
  useGetActiveUserTypesQuery,
  useStartOnboardingMutation,
  useGetMyReviewCommentsQuery,
  useRespondToChangeRequestMutation,
  useResubmitForReviewMutation,
} from '@/store/api/onboardingApi'
import { WithdrawAction } from './WithdrawAction'
```

### 7b. Pending-review card — user-type context + withdraw

Replace the existing `pending_review` block:

```tsx
  if (status.status === 'pending_review') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.pendingReview.title')}</CardTitle>
          <CardDescription>{t('wizard.pendingReview.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{t('wizard.pendingReview.badge')}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t('wizard.pendingReview.info')}</p>
          <Button onClick={() => navigate('/dashboard')}>{t('wizard.pendingReview.goToDashboard')}</Button>
        </CardContent>
      </Card>
    )
  }
```

with:

```tsx
  if (status.status === 'pending_review') {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('wizard.pendingReview.title')}</CardTitle>
          <CardDescription>
            {status.user_type?.name
              ? t('wizard.userTypeContext', { userType: status.user_type.name }) +
                ' · ' +
                t('wizard.pendingReview.description')
              : t('wizard.pendingReview.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{t('wizard.pendingReview.badge')}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">{t('wizard.pendingReview.info')}</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => navigate('/dashboard')}>{t('wizard.pendingReview.goToDashboard')}</Button>
            {status.user_user_type_id && (
              <WithdrawAction
                userUserTypeId={status.user_user_type_id}
                status="pending_review"
                userTypeName={status.user_type?.name || ''}
              />
            )}
          </div>
        </CardContent>
      </Card>
    )
  }
```

### 7c. Change-requested card — user-type context + withdraw

In the `change_requested` header, replace:

```tsx
            <CardDescription>{t('wizard.changeRequested.description')}</CardDescription>
          </CardHeader>
```

with:

```tsx
            <CardDescription>
              {status.user_type?.name
                ? t('wizard.userTypeContext', { userType: status.user_type.name }) +
                  ' · ' +
                  t('wizard.changeRequested.description')
                : t('wizard.changeRequested.description')}
            </CardDescription>
          </CardHeader>
```

Then in the `change_requested` action-buttons block, replace:

```tsx
            {/* Action buttons */}
            <div className="flex flex-wrap gap-3">
              <Button variant="outline" onClick={() => setIsEditingSteps(true)}>
                {t('wizard.changeRequested.editSteps')}
              </Button>
              <Button onClick={handleResubmit} disabled={isResubmitting}>
                {isResubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {t('wizard.changeRequested.resubmit')}
              </Button>
            </div>
```

with:

```tsx
            {/* Action buttons */}
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={() => setIsEditingSteps(true)}>
                {t('wizard.changeRequested.editSteps')}
              </Button>
              <Button onClick={handleResubmit} disabled={isResubmitting}>
                {isResubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {t('wizard.changeRequested.resubmit')}
              </Button>
              {userUserTypeId && (
                <WithdrawAction
                  userUserTypeId={userUserTypeId}
                  status="change_requested"
                  userTypeName={status.user_type?.name || ''}
                />
              )}
            </div>
```

### 7d. In-progress wizard header — user-type context + withdraw

In the main wizard render (the final `return (...)`), update the header `Card` so the inner `CardHeader > div.space-y-4` adds a `CardDescription` with the user-type context next to the title and renders the withdraw link below the progress bar:

```tsx
        <CardHeader>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <CardTitle>{t('wizard.title')}</CardTitle>
                {status.user_type?.name && (
                  <CardDescription>
                    {t('wizard.userTypeContext', { userType: status.user_type.name })}
                  </CardDescription>
                )}
              </div>
              <Badge variant="secondary">
                {t('wizard.stepProgress', {
                  current: status.completed_steps_count + 1,
                  total: status.total_steps_count,
                })}
              </Badge>
            </div>
            <div className="space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-sm text-muted-foreground">
                {t('wizard.progressDescription', {
                  completed: status.completed_steps_count,
                  total: status.total_steps_count,
                })}
              </p>
            </div>
            {status.user_user_type_id && (
              <div className="flex justify-end">
                <WithdrawAction
                  userUserTypeId={status.user_user_type_id}
                  status="in_progress"
                  userTypeName={status.user_type?.name || ''}
                />
              </div>
            )}
          </div>
        </CardHeader>
```

After withdrawal, RTK Query invalidates the `STATUS` tag; the wizard refetches and renders the existing `UserTypeSelection` screen because the user no longer has a non-deleted in-flight `UserUserType`.

---

## 8. Frontend dashboard card — `app/frontend/src/features/onboarding/OnboardingProgressCard.tsx`

Users land on the dashboard before entering the wizard. The progress card must also offer withdrawal so users can bail out without first navigating into `/onboarding`.

### 8a. Import

```typescript
import { WithdrawAction } from './WithdrawAction'
```

### 8b. Change-requested card

Replace the current `change_requested` `CardContent`:

```tsx
        <CardContent className="pt-0">
          <Button asChild size="sm">
            <Link to="/onboarding">{t('progressCard.editSubmission')}</Link>
          </Button>
        </CardContent>
```

with:

```tsx
        <CardContent className="pt-0">
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild size="sm">
              <Link to="/onboarding">{t('progressCard.editSubmission')}</Link>
            </Button>
            {status.user_user_type_id && (
              <WithdrawAction
                userUserTypeId={status.user_user_type_id}
                status="change_requested"
                userTypeName={status.user_type?.name || ''}
              />
            )}
          </div>
        </CardContent>
```

### 8c. In-progress / pending-review card

Replace the tail of the main return block:

```tsx
        {!isPendingReview && (
          <Button asChild className="w-full">
            <Link to="/onboarding">{t('progressCard.continueButton')}</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
```

with:

```tsx
        {!isPendingReview && (
          <Button asChild className="w-full">
            <Link to="/onboarding">{t('progressCard.continueButton')}</Link>
          </Button>
        )}

        {status.user_user_type_id && (isPendingReview || status.status === 'in_progress') && (
          <div className="flex justify-center">
            <WithdrawAction
              userUserTypeId={status.user_user_type_id}
              status={isPendingReview ? 'pending_review' : 'in_progress'}
              userTypeName={status.user_type?.name || ''}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

`approved` and `rejected` are deliberately left without a withdraw entry — they are not self-withdrawable (see "Out of scope" below).

---

## 9. Verification

- Backend: `cd app/backend && make lint` then `make test-fast` — focus on `tests/api_tests/test_onboarding_api.py::test_withdraw_*`, `test_cannot_withdraw_other_org_submission`, and `test_withdraw_then_restart_same_user_type` (the last one depends on the `sqlite_where` model tweak in section 2).
- Frontend: `cd app/frontend && npm run lint` then `npm run dev`. Walk both surfaces:
  - **Dashboard progress card** — for each of `in_progress`, `pending_review`, and `change_requested` states, confirm the card renders the user type and the "Choose a different profile type" link; click it, confirm the dialog, and verify the card disappears / reverts to `UserTypeSelection` behaviour on re-entry.
  - **Wizard at `/onboarding`** — for the same three states, confirm the header shows "Onboarding for {userType}", the withdraw link is visible, and confirming returns the user to `UserTypeSelection`.
- Verify admin queue: when withdrawing from `pending_review`, confirm the admin's review queue no longer shows the phantom item (uses the `onboarding_withdrawn` WebSocket event already wired).

## 10. Out of scope (deliberately)

- Withdrawing from `APPROVED` — that's role revocation and belongs to admin tooling, not self-service.
- Re-opening a `REJECTED` submission — kept terminal. Withdrawal explicitly diverges from rejection: a withdrawing user can re-select the same user type because the soft-deleted row falls outside the partial unique index, but a rejected user cannot.
- Invitation-derived assignments are handled implicitly: invited users are created with `onboarding_status=APPROVED` (see `app/backend/src/api/user.py` invitation block), so the status guard already blocks self-withdrawal of an invite-targeted role.
