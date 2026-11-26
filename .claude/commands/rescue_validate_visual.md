# Validate Visual Match

Compare rescued UI against source project screenshots.

## Arguments
- `$1` - ADW ID

## Instructions

This command validates that the rescued frontend visually matches the source.

### 1. Check Source Screenshots

First, check if source screenshots exist at `rescue/screenshots/source/`.

**If source project can be started:**
1. Start source project (if possible)
2. Capture screenshots of key pages
3. Save to `rescue/screenshots/source/`

**If source cannot run:**
- Note this limitation
- Skip source comparison
- Focus on rescued UI quality check only

### 2. Start Rescued Application

Use `/prepare_app` to start the rescued application:
- Read `.ports.env` for port configuration
- Start backend and frontend
- Wait for services to be healthy

### 3. Capture Rescued Screenshots

Navigate to key pages and capture screenshots:

Pages to capture (based on feature_map.json):
- Login page
- Main dashboard
- Each major feature page
- Settings/profile pages

Save to `rescue/screenshots/rescued/`

### 4. Visual Comparison (if source available)

For each page pair:

1. **Layout Analysis**
   - Overall structure match
   - Component positioning
   - Responsive behavior

2. **Style Consistency**
   - Color palette match
   - Typography match
   - Spacing consistency

3. **Component Fidelity**
   - Buttons and inputs
   - Cards and containers
   - Navigation elements

### 5. Calculate Match Score

```
For each page:
  layout_score = assess_layout_similarity()  # 0-1
  style_score = assess_style_consistency()   # 0-1
  component_score = assess_component_fidelity()  # 0-1

  page_score = (layout_score + style_score + component_score) / 3

  if page_score >= 0.8:
    status = "excellent"
  elif page_score >= 0.6:
    status = "good"
  elif page_score >= 0.4:
    status = "acceptable"
  else:
    status = "poor"

overall_match = average(all page_scores) * 100
```

### 6. Identify Differences

For each page, document:
- Major differences (layout breaks, missing elements)
- Minor differences (color variations, spacing)
- Acceptable differences (improved patterns from template)

## Output

Create `rescue/visual_comparison.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "source_available": true,
  "overall_match_percent": 87.5,
  "pages": [
    {
      "name": "Dashboard",
      "source_screenshot": "rescue/screenshots/source/dashboard.png",
      "rescued_screenshot": "rescue/screenshots/rescued/dashboard.png",
      "scores": {
        "layout": 0.95,
        "style": 0.80,
        "components": 0.90,
        "overall": 0.88
      },
      "status": "excellent",
      "differences": [
        {
          "type": "minor",
          "description": "Button colors slightly different (using template theme)"
        },
        {
          "type": "acceptable",
          "description": "Card shadows updated to template style"
        }
      ]
    },
    {
      "name": "UserProfile",
      "source_screenshot": "rescue/screenshots/source/profile.png",
      "rescued_screenshot": "rescue/screenshots/rescued/profile.png",
      "scores": {
        "layout": 0.90,
        "style": 0.75,
        "components": 0.85,
        "overall": 0.83
      },
      "status": "excellent",
      "differences": [
        {
          "type": "minor",
          "description": "Avatar component uses template circular style"
        }
      ]
    }
  ],
  "summary": {
    "pages_compared": 8,
    "excellent_match": 5,
    "good_match": 2,
    "acceptable_match": 1,
    "poor_match": 0,
    "common_differences": [
      "Button styling (using template theme)",
      "Card shadows (template standard)",
      "Font family (template default)"
    ]
  }
}
```

Report to stdout:

```
=== VISUAL VALIDATION ===

Overall Match: 87.5%

Pages:
  - Dashboard: 88% (excellent)
  - UserProfile: 83% (excellent)
  - PostList: 85% (excellent)
  - Settings: 78% (good)

Common Acceptable Differences:
  - Using template button styles
  - Card shadows standardized
  - Font updated to template default

Major Issues: None

Recommendation: Visual rescue successful
```

## Validation

- Screenshots captured for all key pages
- Comparison JSON exists if source available
- Match percentages calculated
- Differences documented with severity

$ARGUMENTS
