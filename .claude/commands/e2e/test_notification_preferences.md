# E2E Test: Notification Preferences

## Test Description
Validate that users can view and update their notification preferences.

## User Story
As a user
I want to manage my notification preferences
So that I can control how and when I receive notifications

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Notification Preferences

**Steps:**
1. Log in as test user
2. Navigate to `/settings/preferences/notifications`
3. **Screenshot:** Notification preferences page
4. Verify page loads correctly
5. Verify preferences sections visible

**Expected Results:**
- Preferences page loads
- All sections displayed
- Current settings shown

### Test 2: View Global Channel Toggles

**Steps:**
1. Navigate to notification preferences
2. **Screenshot:** Channel toggles
3. Verify channel toggles visible:
   - Email
   - SMS
   - WhatsApp
   - In-App
4. Verify current state shown

**Expected Results:**
- All channel toggles present
- Current states displayed
- Toggles functional

### Test 3: Toggle Email Notifications

**Steps:**
1. Note current Email toggle state
2. Click Email toggle to change state
3. **Screenshot:** Email toggle changed
4. Wait for save
5. Verify success indication
6. Refresh page
7. Verify state persisted

**Expected Results:**
- Toggle changes state
- Change saves automatically
- State persists

### Test 4: Toggle SMS Notifications

**Steps:**
1. Toggle SMS notification setting
2. **Screenshot:** SMS toggle changed
3. Verify change saves
4. Verify affects SMS delivery

**Expected Results:**
- SMS toggle works
- Setting persists

### Test 5: Configure Quiet Hours

**Steps:**
1. Navigate to preferences
2. Locate Quiet Hours section
3. **Screenshot:** Quiet hours settings
4. Toggle "Enable Quiet Hours"
5. Set start time: 22:00
6. Set end time: 08:00
7. Select timezone
8. **Screenshot:** Quiet hours configured
9. Save changes
10. Verify settings saved

**Expected Results:**
- Quiet hours can be enabled
- Time selection works
- Timezone selectable
- Settings persist

### Test 6: Disable Quiet Hours

**Steps:**
1. With quiet hours enabled
2. Toggle to disable
3. **Screenshot:** Quiet hours disabled
4. Verify time fields hidden or disabled
5. Save and verify

**Expected Results:**
- Can disable quiet hours
- Time fields update
- Setting persists

### Test 7: View Category Preferences

**Steps:**
1. Navigate to preferences
2. Locate category preferences section
3. **Screenshot:** Category list
4. Verify categories displayed with:
   - Category name
   - Category description
   - Per-channel toggles
5. Only user-configurable categories shown

**Expected Results:**
- Categories listed
- Per-channel toggles present
- Non-configurable hidden

### Test 8: Update Category Preference

**Steps:**
1. Find a notification category
2. Note current email toggle state
3. Toggle email for that category
4. **Screenshot:** Category preference changed
5. Wait for save
6. Refresh page
7. Verify state persisted

**Expected Results:**
- Category toggle works
- Saves per-category setting
- Persists after refresh

### Test 9: Multiple Category Updates

**Steps:**
1. Update email for Category A
2. Update SMS for Category B
3. Update In-App for Category C
4. **Screenshot:** Multiple changes
5. Verify all changes saved
6. Refresh and verify

**Expected Results:**
- Multiple updates work
- All changes persist
- No conflicts

### Test 10: Loading State

**Steps:**
1. Navigate to notification preferences
2. **Screenshot:** Loading state
3. Observe skeleton loaders
4. Wait for data
5. Verify content loads

**Expected Results:**
- Loading state shown
- Smooth data load
- No empty flash

### Test 11: Save Error Handling

**Steps:**
1. Make a preference change
2. Simulate network error
3. **Screenshot:** Error state
4. Verify error message
5. Verify can retry

**Expected Results:**
- Error feedback shown
- Can retry save
- Previous state preserved

### Test 12: Global Toggle Affects Categories

**Steps:**
1. Disable Email globally
2. Check category Email toggles
3. **Screenshot:** Category toggles state
4. Verify category toggles:
   - Show disabled state, OR
   - Still editable (override)
5. Re-enable Email globally
6. Verify categories update

**Expected Results:**
- Global affects categories
- Clear visual relationship
- Consistent behavior

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/preferences` | Get user preferences |
| PUT | `/notifications/preferences` | Update user preferences |
| GET | `/notifications/preferences/categories` | Get category preferences |
| PUT | `/notifications/preferences/categories/{id}` | Update category preference |

## Request/Response Format

**Get Preferences Response:**
```json
{
  "email_enabled": true,
  "sms_enabled": false,
  "whatsapp_enabled": false,
  "in_app_enabled": true,
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "timezone": "America/New_York"
}
```

**Update Preferences Request:**
```json
{
  "email_enabled": true,
  "sms_enabled": true,
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "timezone": "America/New_York"
}
```

**Category Preferences Response:**
```json
{
  "items": [
    {
      "category_id": "cat-uuid",
      "category_name": "Security Alerts",
      "category_description": "Important security notifications",
      "email_enabled": true,
      "sms_enabled": false,
      "whatsapp_enabled": false,
      "in_app_enabled": true
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Email toggle | Switch for email channel |
| SMS toggle | Switch for SMS channel |
| WhatsApp toggle | Switch for WhatsApp channel |
| In-App toggle | Switch for in-app channel |
| Quiet hours enable | Switch for quiet hours |
| Start time select | Select for start time |
| End time select | Select for end time |
| Timezone select | Select for timezone |
| Category section | Section containing categories |
| Category name | Text showing category name |
| Category channel toggle | Per-channel switch in category row |
| Save button | `getByRole('button', { name: /save/i })` if manual save |
| Loading skeleton | Skeleton loader components |

## Success Criteria

- All global channel toggles work
- Quiet hours can be configured
- Timezone selection works
- Category preferences displayed
- Per-category toggles work
- Changes persist after refresh
- Loading states shown
- Errors handled gracefully

## Notes

- Verify auto-save vs manual save behavior
- Test timezone edge cases
- Check quiet hours validation
- Verify i18n for all labels
- Test with categories that aren't user-configurable
- Verify channel availability based on org settings
