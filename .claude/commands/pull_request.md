# Create Pull Request

Based on the `Instructions` below, take the `Variables` follow the `Run` section to create a pull request. Then follow the `Report` section to report the results of your work.

## Variables

branch_name: $ARGUMENT
issue: $ARGUMENT
plan_file: $ARGUMENT
adw_id: $ARGUMENT
smoke_test_data: $ARGUMENT

## Instructions

- Generate a pull request title in the format: `<issue_type>: #<issue_number> - <issue_title>`
- The PR body should include:
  - A summary section with the issue context
  - Link to the implementation `plan_file` if it exists
  - Reference to the issue (Closes #<issue_number>)
  - ADW tracking ID
  - A checklist of what was done
  - A summary of key changes made
  - **Smoke Test Screenshots section** (if smoke tests were run - see below)
- Extract issue number, type, and title from the issue JSON
- Examples of PR titles:
  - `feat: #123 - Add user authentication`
  - `bug: #456 - Fix login validation error`
  - `chore: #789 - Update dependencies`
  - `test: #1011 - Test xyz`
- Don't mention Claude Code in the PR body - let the author get credit for this.

### Smoke Test Screenshots

The `smoke_test_data` variable is a JSON object with:
- `passed`: number of passed tests
- `failed`: number of failed tests
- `screenshot_urls`: array of public URLs to screenshots

If `screenshot_urls` is not empty, you MUST include a "Smoke Test Screenshots" section in the PR body with:
- A header: `## Smoke Test Screenshots`
- Test results summary: `✅ X passed, ❌ Y failed`
- Each screenshot embedded as a markdown image: `![Smoke Test Screenshot N](url)`

Example:
```markdown
## Smoke Test Screenshots

✅ 3 passed, ❌ 0 failed

![Smoke Test Screenshot 1](https://example.com/screenshot1.png)
![Smoke Test Screenshot 2](https://example.com/screenshot2.png)
```

## Run

1. Run `git diff origin/main...HEAD --stat` to see a summary of changed files
2. Run `git log origin/main..HEAD --oneline` to see the commits that will be included
3. Run `git diff origin/main...HEAD --name-only` to get a list of changed files
4. Run `git push -u origin <branch_name>` to push the branch
5. Set GH_TOKEN environment variable from GITHUB_PAT if available, then run `gh pr create --title "<pr_title>" --body "<pr_body>" --base main` to create the PR
6. Capture the PR URL from the output

## Report

Return ONLY the PR URL that was created (no other text)
