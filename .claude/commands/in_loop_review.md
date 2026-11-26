# In-Loop Review

Quick checkout and review workflow for agent work validation.

## Variables

branch: $ARGUMENTS

## Workflow

IMPORTANT: If no branch is provided, stop execution and report that a branch argument is required.

Follow these steps to quickly checkout and review work done by agents:

### Step 1: Pull and Checkout Branch
- Run `git fetch origin` to get latest remote changes
- Run `git checkout {branch}` to switch to the target branch

### Step 2: Prepare Application
- Read and execute: `.claude/commands/prepare_app.md` to setup the application for review

### Step 3: Start Application
- Read and execute: `.claude/commands/start.md` to start the application for testing

### Step 4: Manual Review
- The application is now running and ready for manual review
- Determine the frontend port: if `.ports.env` exists, source it and use `FRONTEND_PORT`; otherwise default to `5173`
- Print the URL and open it for the engineer using whichever launcher is available (cross-platform - do NOT assume macOS `open`):
  ```bash
  URL="http://localhost:${FRONTEND_PORT:-5173}"
  echo "Open the application for review at: $URL"
  (command -v xdg-open >/dev/null && xdg-open "$URL") \
    || (command -v open >/dev/null && open "$URL") \
    || echo "No browser launcher found - open $URL manually"
  ```

## Report

Report steps you've taken to prepare the application for review.