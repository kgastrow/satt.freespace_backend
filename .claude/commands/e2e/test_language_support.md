# E2E Test: Language Support

Test the new language support functionality (isiZulu, Sepedi, isiXhosa) to verify that all three South African languages are properly integrated into the application's internationalization system.

## User Story

As a user who speaks isiZulu, Sepedi, or isiXhosa
I want to use the application in my native language
So that I can interact with the system more naturally and effectively

## Test Prerequisites

- Frontend application must be running (default: http://localhost:5173)
- Backend API must be running (default: http://localhost:8000)
- Chrome/Chromium browser must be available
- All translation files must be present in `app/frontend/src/locales/{zu,nso,xh}/`

## Test Steps

### Part 1: Verify Language Switcher Displays All Languages

1. Navigate to the application home page
   ```python
   await page.goto('http://localhost:5173')
   ```

2. Wait for the page to load and locate the language switcher button
   ```python
   language_button = page.locator('button:has-text("EN"), button:has-text("DE"), button:has-text("ZU"), button:has-text("NSO"), button:has-text("XH")')
   await language_button.wait_for(state='visible', timeout=5000)
   ```

3. Click the language switcher to open the dropdown
   ```python
   await language_button.click()
   ```

4. **Verify** all five languages appear in the dropdown:
   - English
   - Deutsch
   - isiZulu
   - Sepedi
   - isiXhosa

   ```python
   await expect(page.locator('text=English')).to_be_visible()
   await expect(page.locator('text=Deutsch')).to_be_visible()
   await expect(page.locator('text=isiZulu')).to_be_visible()
   await expect(page.locator('text=Sepedi')).to_be_visible()
   await expect(page.locator('text=isiXhosa')).to_be_visible()
   ```

5. Take a screenshot showing all five languages in the dropdown
   ```python
   await page.screenshot(path='screenshots/language_switcher_all_languages.png')
   ```

### Part 2: Switch to isiZulu and Verify UI Updates

6. Click on "isiZulu" in the language dropdown
   ```python
   await page.locator('text=isiZulu').click()
   ```

7. Wait for the language to change
   ```python
   await page.wait_for_timeout(1000)
   ```

8. **Verify** the language button now shows "ZU"
   ```python
   await expect(page.locator('button:has-text("ZU")')).to_be_visible()
   ```

9. **Verify** UI text has been translated to isiZulu
   - Check for translated strings in common namespace
   - Navigation elements should be in isiZulu
   - Button labels should be in isiZulu

10. Take a screenshot of the page in isiZulu
    ```python
    await page.screenshot(path='screenshots/homepage_isizulu.png')
    ```

### Part 3: Switch to Sepedi and Verify UI Updates

11. Open the language switcher again
    ```python
    language_button = page.locator('button:has-text("ZU")')
    await language_button.click()
    ```

12. Click on "Sepedi" in the language dropdown
    ```python
    await page.locator('text=Sepedi').click()
    ```

13. Wait for the language to change
    ```python
    await page.wait_for_timeout(1000)
    ```

14. **Verify** the language button now shows "NSO"
    ```python
    await expect(page.locator('button:has-text("NSO")')).to_be_visible()
    ```

15. **Verify** UI text has been translated to Sepedi
    - Check for translated strings in common namespace
    - Navigation elements should be in Sepedi
    - Button labels should be in Sepedi

16. Take a screenshot of the page in Sepedi
    ```python
    await page.screenshot(path='screenshots/homepage_sepedi.png')
    ```

### Part 4: Switch to isiXhosa and Verify UI Updates

17. Open the language switcher again
    ```python
    language_button = page.locator('button:has-text("NSO")')
    await language_button.click()
    ```

18. Click on "isiXhosa" in the language dropdown
    ```python
    await page.locator('text=isiXhosa').click()
    ```

19. Wait for the language to change
    ```python
    await page.wait_for_timeout(1000)
    ```

20. **Verify** the language button now shows "XH"
    ```python
    await expect(page.locator('button:has-text("XH")')).to_be_visible()
    ```

21. **Verify** UI text has been translated to isiXhosa
    - Check for translated strings in common namespace
    - Navigation elements should be in isiXhosa
    - Button labels should be in isiXhosa

22. Take a screenshot of the page in isiXhosa
    ```python
    await page.screenshot(path='screenshots/homepage_isixhosa.png')
    ```

### Part 5: Test Language Persistence

23. Reload the page while still on isiXhosa
    ```python
    await page.reload()
    ```

24. Wait for the page to load
    ```python
    await page.wait_for_load_state('networkidle')
    ```

25. **Verify** the language remains as isiXhosa (XH) after reload
    ```python
    await expect(page.locator('button:has-text("XH")')).to_be_visible()
    ```

26. **Verify** localStorage has the correct language preference stored
    ```python
    language_storage = await page.evaluate('() => localStorage.getItem("i18nextLng")')
    assert language_storage == 'xh', f"Expected 'xh' in localStorage, got {language_storage}"
    ```

### Part 6: Test Language Switching on Different Pages

27. Navigate to a different page (e.g., login page)
    ```python
    await page.goto('http://localhost:5173/auth/login')
    await page.wait_for_load_state('networkidle')
    ```

28. **Verify** the language remains isiXhosa on the login page
    ```python
    await expect(page.locator('button:has-text("XH")')).to_be_visible()
    ```

29. Take a screenshot of the login page in isiXhosa
    ```python
    await page.screenshot(path='screenshots/login_page_isixhosa.png')
    ```

30. Switch to English for comparison
    ```python
    await page.locator('button:has-text("XH")').click()
    await page.locator('text=English').click()
    await page.wait_for_timeout(1000)
    ```

31. Take a screenshot of the login page in English
    ```python
    await page.screenshot(path='screenshots/login_page_english.png')
    ```

### Part 7: Verify Fallback Behavior

32. Switch back to one of the new languages
    ```python
    await page.locator('button:has-text("EN")').click()
    await page.locator('text=isiZulu').click()
    ```

33. Navigate through different sections of the app
    - Dashboard
    - Settings
    - Admin pages (if accessible)

34. **Verify** that if any translation keys are missing, they fallback to English
    - No "undefined" or raw translation keys should appear
    - Missing translations should show the English text

35. Take screenshots of multiple pages in isiZulu to verify comprehensive translation
    ```python
    await page.screenshot(path='screenshots/app_isizulu_comprehensive.png')
    ```

### Part 8: Test Lazy Loading of Translation Files

36. Open browser DevTools Network panel (programmatically or note for manual test)
    ```python
    # This would typically be verified manually or with browser CDP
    # Check that translation JSON files are loaded on-demand
    ```

37. Switch to Sepedi
    ```python
    await page.locator('button:has-text("ZU")').click()
    await page.locator('text=Sepedi').click()
    ```

38. **Verify** in Network tab that Sepedi translation files are loaded:
    - `nso/common.json`
    - Other namespace files loaded as needed (auth, dashboard, etc.)

39. **Verify** translations are cached and not re-fetched on subsequent navigation

## Expected Results

1. ✅ All five languages (English, Deutsch, isiZulu, Sepedi, isiXhosa) appear in the language switcher dropdown
2. ✅ Clicking on any South African language successfully switches the UI language
3. ✅ The language button shows the correct ISO language code (ZU, NSO, XH)
4. ✅ All UI text updates to reflect the selected language
5. ✅ Language preference persists across page reloads
6. ✅ Language preference persists across different pages/routes
7. ✅ Missing translation keys fallback to English gracefully
8. ✅ Translation files are lazy-loaded on demand
9. ✅ No console errors appear when switching languages
10. ✅ No TypeScript errors in the browser console

## Error Scenarios to Test

1. **Missing Translation File**: If a translation file is missing, the app should fallback to English
2. **Invalid Language Code**: Attempting to manually set an invalid language code should fallback to English
3. **Network Failure**: If translation files fail to load, show appropriate error or fallback
4. **Rapid Language Switching**: Quickly clicking between languages should not break the UI

## Acceptance Criteria

- [ ] All three new languages (isiZulu, Sepedi, isiXhosa) appear in the language switcher
- [ ] Language switching works correctly for all five languages
- [ ] Language preference persists in localStorage
- [ ] Language persists across page reloads and navigation
- [ ] UI translations render correctly in all languages
- [ ] No console errors when switching languages
- [ ] Fallback to English works for missing keys
- [ ] Translation files are lazy-loaded efficiently

## Notes

- This E2E test validates the full language switching workflow from a user's perspective
- Translation quality should be reviewed separately by native speakers
- Performance of lazy loading should be monitored in production
- Consider adding visual regression testing for translated UI in future iterations
