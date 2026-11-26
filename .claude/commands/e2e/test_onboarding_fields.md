# E2E Test: Onboarding Field Rendering

## Test Description
Validate that all onboarding field types render correctly and accept valid input.

## User Story
As a user
I want to fill out various field types
So that I can provide all required information

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with onboarding:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Onboarding step with multiple field types configured
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Text Field (string)

**Steps:**
1. Find a text input field
2. **Screenshot:** Text field
3. Enter text: "Test Value"
4. Verify value displayed
5. Test max length validation (if configured)

**Expected Results:**
- Text input works
- Value displays
- Validation works

### Test 2: Email Field

**Steps:**
1. Find email field
2. **Screenshot:** Email field
3. Enter valid email: "test@example.com"
4. Verify accepted
5. Enter invalid: "notanemail"
6. **Screenshot:** Email validation error
7. Verify error message

**Expected Results:**
- Email validation works
- Valid accepted
- Invalid rejected

### Test 3: Number Field

**Steps:**
1. Find number input
2. **Screenshot:** Number field
3. Enter number: 42
4. Verify accepted
5. Test min/max validation (if configured)
6. Enter non-numeric
7. Verify handling

**Expected Results:**
- Number input works
- Min/max enforced
- Invalid rejected

### Test 4: URL Field

**Steps:**
1. Find URL field
2. **Screenshot:** URL field
3. Enter valid URL: "https://example.com"
4. Verify accepted
5. Enter invalid URL: "not a url"
6. **Screenshot:** URL validation error

**Expected Results:**
- URL validation works
- Valid URLs accepted
- Invalid rejected

### Test 5: Textarea Field

**Steps:**
1. Find textarea field
2. **Screenshot:** Textarea field
3. Enter multi-line text
4. Verify text preserved
5. Test max length (if configured)

**Expected Results:**
- Textarea works
- Multi-line preserved
- Length validation works

### Test 6: Select/Dropdown Field

**Steps:**
1. Find select field
2. **Screenshot:** Select field closed
3. Click to open dropdown
4. **Screenshot:** Options visible
5. Select an option
6. Verify selection shown

**Expected Results:**
- Dropdown opens
- Options displayed
- Selection works

### Test 7: Checkbox Field

**Steps:**
1. Find checkbox field
2. **Screenshot:** Unchecked state
3. Click to check
4. **Screenshot:** Checked state
5. Click to uncheck
6. Verify toggle works

**Expected Results:**
- Checkbox toggles
- State visible
- Persists on submit

### Test 8: Date Picker Field

**Steps:**
1. Find date field
2. **Screenshot:** Date field
3. Click to open picker
4. **Screenshot:** Date picker open
5. Select a date
6. Verify date displayed
7. Test min/max date (if configured)

**Expected Results:**
- Date picker opens
- Can select date
- Validation works

### Test 9: Phone Field

**Steps:**
1. Find phone field
2. **Screenshot:** Phone field
3. Enter phone: "+1234567890"
4. Verify accepted
5. Test format validation

**Expected Results:**
- Phone input works
- Format validation
- Country code support

### Test 10: Radio Button Field

**Steps:**
1. Find radio button group
2. **Screenshot:** Radio options
3. Select first option
4. **Screenshot:** First selected
5. Select second option
6. Verify first deselected
7. Verify only one selected

**Expected Results:**
- Radio buttons work
- Mutually exclusive
- Selection visible

### Test 11: Multi-Select Field

**Steps:**
1. Find multi-select field
2. **Screenshot:** Multi-select
3. Select first option
4. Select second option
5. **Screenshot:** Multiple selected
6. Verify both shown
7. Test max selections (if configured)

**Expected Results:**
- Multiple selections work
- All shown
- Max enforced

### Test 12: File Upload Field

**Steps:**
1. Find file upload field
2. **Screenshot:** Upload zone
3. Click or drag file to upload
4. **Screenshot:** File uploading
5. Wait for upload
6. **Screenshot:** File uploaded
7. Verify file info shown

**Expected Results:**
- Upload zone visible
- Can select/drop file
- Progress shown
- File info displayed

### Test 13: Optional Field Indicator

**Steps:**
1. Find optional field
2. **Screenshot:** Optional field
3. Verify no asterisk or "optional" label
4. Leave field empty
5. Submit form
6. Verify no validation error

**Expected Results:**
- Optional clearly marked
- Can be left empty
- No error when empty

### Test 14: Required Field Indicator

**Steps:**
1. Find required field
2. **Screenshot:** Required field
3. Verify asterisk or required indicator
4. Leave field empty
5. Try to submit
6. **Screenshot:** Required error

**Expected Results:**
- Required clearly marked
- Cannot be empty
- Error shown when empty

### Test 15: Field Description/Help Text

**Steps:**
1. Find field with description
2. **Screenshot:** Field with help text
3. Verify description visible
4. Verify helps user understand field

**Expected Results:**
- Help text shown
- Clear and helpful
- Positioned appropriately

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/onboarding/status` | Get step with field definitions |
| POST | `/onboarding/steps/{id}/submit` | Submit with field data |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Text input | `input[type="text"]` or `getByLabelText()` |
| Email input | `input[type="email"]` |
| Number input | `input[type="number"]` |
| URL input | `input[type="url"]` |
| Textarea | `textarea` |
| Select | Select component |
| Checkbox | `input[type="checkbox"]` |
| Date picker | Date input component |
| Phone input | Phone input component |
| Radio buttons | `input[type="radio"]` |
| Multi-select | Multi-select component |
| File upload | FileUploader component / dropzone |
| Required indicator | Asterisk or "required" text |
| Optional indicator | "Optional" label |
| Help text | Description element |
| Validation error | Error message element |

## Success Criteria

- All 11 field types render correctly
- Text, email, number, URL inputs work
- Textarea accepts multi-line
- Select dropdown works
- Checkbox toggles
- Date picker selects dates
- Phone input accepts numbers
- Radio buttons are exclusive
- Multi-select allows multiple
- File upload works
- Required/optional indicators shown
- Validation messages display

## Notes

- Test with field configuration variations
- Verify drag-drop for file upload
- Check date format handling
- Test phone number formatting
- Verify file type restrictions
- Check i18n for validation messages
