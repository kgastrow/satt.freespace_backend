# E2E Test: Freespace Test Push and Announcement

## Test Description
Validate the Test push and Announcement dialogs in the site header: device target by id ending, topic target and announcement with typed topic confirmation, result wording, and permission gating.

## User Story
As an administrator
I want to send a test push to my own phone or an announcement to the site
So that I can verify the push path without waiting for a real advisory

## Prerequisites
- Backend running with FCM configured (or FCM mocked); frontend running
- A site with topic `{topic}` (Overview or Settings tab shows it) and a registered phone that has opted in; note the last 6 characters of the device id shown in the app's settings
- An administrator (`site_push:test`, `site_push:announce`) and a viewer (`sites:read` only)

## Test Steps

### Test 1: Test Push to One Device
1. Login as administrator, open a site, click "Test push" in the page header
2. **Screenshot:** dialog with "One device" selected and the "Last 6 characters of the device id" field
3. Verify "Send test push" is disabled; type 5 characters, still disabled; type 6, enabled
4. Click send
5. **Screenshot:** result "Accepted by FCM" with the FCM time and the note that this does not confirm a phone received it
6. Verify the phone shows the test notification; open the Event log tab and verify a "Test push" event

### Test 2: Device Errors
1. Reopen the dialog, enter `zzzzzz` (no such device); verify the translated message "No device matches this id suffix" and the dialog stays open
2. Enter an ending shared by two devices (if available); verify the "More than one device matches" message
3. Enter the ending of a device without a token; verify "The device has no valid push token"

### Test 3: Topic Test Push Needs Confirmation
1. Choose "Every subscriber of the site topic"
2. **Screenshot:** warning that it reaches every subscribed phone of the site at once, and the confirmation field
3. Type a wrong topic; verify the send button stays disabled. Type the exact topic name; verify it enables
4. Send; verify "Accepted by FCM"

### Test 4: Announcement
1. Click "Announcement"; verify send is disabled with an empty message
2. Type a message (counter shows "n of 500 characters") and an optional title, type the topic name to confirm
3. Send; verify "Accepted by FCM" and an "Announcement" event in the log
4. Simulate an FCM failure (invalid credentials); verify the translated error ("The push credential was rejected by FCM") and that the failed attempt still appears in the event log

### Test 5: Gating
1. Login as viewer; open a site
2. Verify neither "Test push" nor "Announcement" is in the header
3. Login as a user with only `site_push:test`; verify only "Test push" is shown

## Success Criteria
- Topic and announcement sends cannot be submitted without typing the topic name
- Results are worded "accepted by FCM"; each backend error shows its own message
- No device id is echoed back anywhere
