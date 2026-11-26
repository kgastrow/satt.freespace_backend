# E2E Test: Locale Persistence

## Test Description
Validate that the user's selected language persists across page reloads and browser sessions.

## User Story
As a user
I want my language preference to be remembered
So that I don't have to change the language every time I visit

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Default Language Detection

**Steps:**
1. Clear localStorage (especially `i18nextLng` key)
2. Navigate to the application
3. **Screenshot:** Initial language
4. Verify language detected from browser
5. Verify UI displays in detected language

**Expected Results:**
- Browser language detected
- UI shows in appropriate language
- Falls back to English if not supported

### Test 2: Change Language

**Steps:**
1. Navigate to application
2. Find language switcher in header
3. **Screenshot:** Language switcher
4. Click to open language dropdown
5. **Screenshot:** Language options
6. Verify 5 languages shown:
   - English
   - Deutsch
   - isiZulu
   - Sepedi
   - isiXhosa
7. Select "Deutsch"
8. **Screenshot:** German UI

**Expected Results:**
- All languages listed
- Selection works
- UI updates to German

### Test 3: Verify localStorage Persistence

**Steps:**
1. Change language to "Deutsch"
2. Open browser developer tools
3. Check localStorage for `i18nextLng` key
4. **Screenshot:** localStorage value
5. Verify value is "de"

**Expected Results:**
- `i18nextLng` key exists
- Value matches selected language
- Stored in localStorage

### Test 4: Page Reload Persistence

**Steps:**
1. Set language to "isiZulu"
2. **Screenshot:** Zulu UI
3. Reload the page (F5 or Ctrl+R)
4. **Screenshot:** After reload
5. Verify language is still "isiZulu"
6. Verify UI displays in Zulu

**Expected Results:**
- Language persists after reload
- No reset to default
- UI stays in selected language

### Test 5: Navigate Between Pages

**Steps:**
1. Set language to "Sepedi"
2. Navigate to Dashboard
3. **Screenshot:** Dashboard in Sepedi
4. Navigate to Files
5. **Screenshot:** Files in Sepedi
6. Navigate to Settings
7. **Screenshot:** Settings in Sepedi
8. Verify language consistent across all pages

**Expected Results:**
- Language stays same across navigation
- All pages translated
- No flickering or reset

### Test 6: New Tab Persistence

**Steps:**
1. Set language to "isiXhosa"
2. Open new tab
3. Navigate to application URL
4. **Screenshot:** New tab language
5. Verify language is "isiXhosa"

**Expected Results:**
- Same language in new tab
- localStorage shared across tabs
- Consistent experience

### Test 7: Session Persistence

**Steps:**
1. Set language to "Deutsch"
2. Log out
3. **Screenshot:** Logout page in German
4. Log back in
5. **Screenshot:** After login
6. Verify language is still "Deutsch"

**Expected Results:**
- Language persists across login/logout
- Independent of auth state
- Stored client-side

### Test 8: Browser Close Persistence

**Steps:**
1. Set language to "isiZulu"
2. Close browser completely
3. Reopen browser
4. Navigate to application
5. **Screenshot:** After browser restart
6. Verify language is still "isiZulu"

**Expected Results:**
- localStorage survives browser close
- Language preference retained
- Seamless experience

### Test 9: Change Language via Settings

**Steps:**
1. Navigate to `/settings/preferences/language`
2. **Screenshot:** Language settings page
3. Select different language from radio options
4. **Screenshot:** New language selected
5. Verify UI updates immediately
6. Reload page
7. Verify language persists

**Expected Results:**
- Settings page language selection works
- Syncs with localStorage
- Persists on reload

### Test 10: Multiple Language Changes

**Steps:**
1. Set language to English
2. Change to Deutsch
3. Change to isiZulu
4. Change to Sepedi
5. Change to isiXhosa
6. **Screenshot:** Final language (isiXhosa)
7. Reload page
8. Verify shows isiXhosa (last selection)

**Expected Results:**
- Each change updates localStorage
- Last selection persisted
- No stale values

### Test 11: Invalid localStorage Value

**Steps:**
1. Open developer tools
2. Set localStorage `i18nextLng` to invalid value "xx"
3. Reload the application
4. **Screenshot:** After invalid value
5. Verify falls back to English or browser language

**Expected Results:**
- Gracefully handles invalid value
- Falls back to default
- No crash or error

### Test 12: Clear localStorage

**Steps:**
1. Set language to "Deutsch"
2. Open developer tools
3. Clear localStorage
4. Reload application
5. **Screenshot:** After clearing
6. Verify falls back to browser language

**Expected Results:**
- Detects browser language
- No error on missing key
- Uses fallback correctly

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| - | - | Locale is client-side only |

## Technical Details

**Storage Mechanism:**
- Key: `i18nextLng`
- Storage: `localStorage`
- Detection order: localStorage → navigator language
- Fallback: English ('en')

**Supported Languages:**
| Code | Display Name |
|------|--------------|
| en | English |
| de | Deutsch |
| zu | isiZulu |
| nso | Sepedi |
| xh | isiXhosa |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Language switcher | Language dropdown button |
| Current language | Displayed language code/name |
| Language options | Dropdown menu items |
| English option | `getByRole('menuitem', { name: /english/i })` |
| German option | `getByRole('menuitem', { name: /deutsch/i })` |
| Zulu option | `getByRole('menuitem', { name: /isizulu/i })` |
| Sepedi option | `getByRole('menuitem', { name: /sepedi/i })` |
| Xhosa option | `getByRole('menuitem', { name: /isixhosa/i })` |
| Settings language page | Language radio group |
| Page content | Any translatable text |

## Success Criteria

- Language selection works for all 5 languages
- Selection stored in localStorage
- Persists across page reloads
- Persists across navigation
- Persists in new tabs
- Persists across login/logout
- Persists after browser restart
- Handles invalid/missing values gracefully
- Falls back to browser language or English

## Notes

- Test in incognito mode for clean state
- Verify RTL languages if added in future
- Check performance of language switching
- Verify no flash of untranslated content
- Test with browser language set to different values
- i18next handles all persistence automatically

