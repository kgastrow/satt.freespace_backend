# Resolve Build Error

Fix a specific TypeScript/build error using the provided error details.

## Instructions

1. **Analyze the Build Error**
   - Review the file path, line number, error code, and message from the `Build Error Input`
   - Understand what the TypeScript compiler is complaining about
   - Common errors include:
     - `TS2741`: Property missing in type (interface changed, mock incomplete)
     - `TS2345`: Argument type mismatch
     - `TS2339`: Property does not exist on type
     - `TS2322`: Type not assignable

2. **Context Discovery**
   - Read the file at the specified line to understand the context
   - If the error mentions a type/interface, find and read its definition
   - Check recent changes: `git diff origin/main -- <file_path>`
   - Look for related files that might need the same fix

3. **Identify Root Cause**
   - For `TS2741` (missing property): An interface was extended but existing usages weren't updated
   - For type mismatches: A type changed or a mock is incomplete
   - Determine if this is a single-file fix or affects multiple files

4. **Fix the Issue**
   - Make minimal, targeted changes to resolve only this build error
   - If the fix requires adding a property to multiple mock objects, fix ALL occurrences in the file
   - Ensure the fix maintains type safety (don't use `any` or `as unknown`)
   - Follow existing code patterns in the file

5. **Validate the Fix**
   - Run `cd app/frontend && npm run build` to confirm the error is resolved
   - Check that no NEW errors were introduced
   - If new errors appear in the same file, fix them too

## Build Error Input

$ARGUMENTS

## Report

Provide a concise summary of:
- Root cause identified (e.g., "AuthState interface added 'sso' property but test mocks weren't updated")
- Specific fix applied (e.g., "Added sso: { isLoading: false, error: null, selectedProvider: null } to 3 mock objects")
- Confirmation that build now passes for this file
