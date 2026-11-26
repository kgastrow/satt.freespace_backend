# E2E Test: Freespace Occupancy History Chart

## Test Description
Validate the History tab: day picker, occupancy chart for the site and its zones with trigger and reset reference lines, gaps for missing data, legend toggles, table view, light and dark theme.

## User Story
As an operator
I want to see how a site filled up over a day
So that I can tune the trigger and reset levels against reality

## Prerequisites
- Backend and frontend running
- A site with a day of occupancy data containing a hole of at least 30 minutes (stop ingesting for that time, or use the simulator and the mock clock), and an empty day
- A user holding `sites:read`

## Test Steps

### Test 1: Chart for Today
1. Login, open a site, click the "History" tab (`/admin/sites/{id}/history`)
2. **Screenshot:** chart with a thick site line, thinner zone lines, a legend above, time axis in the site's time zone, 0-100% axis
3. Verify two dashed horizontal lines at the site's trigger and reset percentages and legend entries "Trigger 90%" and "Reset 80%"
4. Hover the chart; verify a tooltip with the time and every series value

### Test 2: Gaps Are Gaps
1. Choose the day with the hole
2. Verify the line is broken across the hole (not drawn through it, not dropped to 0%)
3. Click "Show as table"; verify rows inside the hole are absent or read "No data", never "0%"

### Test 3: Day Picker
1. Click "Previous day"; verify the chart changes and the URL request carries `?date=yyyy-MM-dd`
2. Verify "Next day" is disabled on today and "Today" returns to the current day
3. Pick a day without data; verify the empty message and no chart

### Test 4: Legend Toggles
1. Click a zone in the legend; verify its line disappears, the legend entry is struck through and `aria-pressed` is false; click again to restore

### Test 5: Theme
1. Switch to dark theme; **Screenshot:** series colours remain distinguishable on the dark surface, axis text and reference lines are readable
2. Switch back to light

## Success Criteria
- Gaps are never drawn as zero or bridged
- Trigger and reset levels come from the site's settings
- Chart has a text alternative (table view) and legend entries are not colour-only
