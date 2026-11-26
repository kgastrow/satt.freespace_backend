# E2E Test: Freespace Event Log

## Test Description
Validate the event log tab of a site: filters (type, reason, period), pagination, expandable row detail and CSV export of the current filter.

## User Story
As an operator
I want to see what the engine decided and why
So that I can explain every push, and every push that was not sent

## Prerequisites
- Backend and frontend running; a site with events (cross the trigger on a shadow site, or use the simulator scenarios AT-02, AT-03 and AT-05)
- A user holding `sites:read` and `site_events:read` (Viewer, Operator or Administrator)

## Test Steps

### Test 1: Open the Log
1. Login, navigate to `/admin/sites`, open a site, click the "Event log" tab (`/admin/sites/{id}/events`)
2. **Screenshot:** table with Time, Type, Reason, Zone and Repeats columns, newest first
3. Verify the range text ("1-25 of N") and the page indicator

### Test 2: Filters
1. Set Type to "Candidate"; verify every row shows type "Candidate" and the page returns to 1
2. Set Reason to "Site not managed (shadow)" (or "No material change"); verify rows narrow further
3. Set Period to "Last 24 hours"; verify older rows disappear
4. Choose Period "Custom days", pick a first day after the last day; verify the inline message and no request is sent
5. Fix the days; verify results. Click "Clear filters"; verify the full log returns

**Expected:** request `GET /admin/sites/{id}/events?type=CANDIDATE&reason=...&start=...` (start/end are the site-time-zone day boundaries).

### Test 3: Row Detail
1. Click the expand chevron of a candidate or advisory row
2. **Screenshot:** detail with the rendered message, "Occurrences" count, "Devices by outcome" badges (for example "Accepted by FCM 12", "Cooldown 3"), fan-out status with FCM time, and figures
3. Verify the wording says "Accepted by FCM" and the word "delivered" appears nowhere
4. Verify no device id, suffix or token is shown anywhere in the detail
5. Collapse the row; verify the detail disappears

### Test 4: Pagination
1. On a site with more than 25 events click "Next"; verify "26-50 of N" and the Previous button enabled
2. Click "Previous"; verify the first page again

### Test 5: CSV Export
1. Apply Type "State change", click "Export CSV"
2. Verify a file `events-{site-slug}.csv` is downloaded (request carries the bearer token; it is not a bare link)
3. Open it: header row `occurred_at,last_seen_at,repeat_count,type,...`; only STATE_CHANGE rows; no device data
4. Make the filter match more than 50,000 events (or stub the API) and verify the translated "narrow the period" message

### Test 6: Permissions
1. Login as a user without `site_events:read`; verify the "Event log" tab is not shown and `/admin/sites/{id}/events` redirects or shows no access

## Success Criteria
- Filters, paging and export all use the same filter state
- Wording is "accepted by FCM", never "delivered"; no device identifiers anywhere
