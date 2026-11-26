# Cleanup ADW Worktrees

Clean up isolated ADW worktrees and their associated resources, including databases.

## Variables

action: $ARGUMENT (all|specific|list)
adw_id: $ARGUMENT (optional, required if action is "specific")

## Instructions

Manage git worktrees created by isolated ADW workflows:
- If action is "list": Show all worktrees under trees/ directory
- If action is "specific": Remove the specific worktree for the given adw_id
- If action is "all": Remove all worktrees under trees/ directory

**IMPORTANT**: Each ADW workflow has an isolated database that must be dropped during cleanup.

## Run

Based on the action:

### List worktrees
If action is "list":
- Run `git worktree list | grep "trees/"` to show isolated worktrees
- List the contents of the trees/ directory with sizes
- Show associated database names (format: appdb_{last_8_chars_of_adw_id})

### Remove specific worktree
If action is "specific" and adw_id is provided:
1. **Kill any running processes from this worktree first**:
   ```bash
   # Kill Python processes (backend, ARQ workers, multiprocessing children)
   pkill -f "trees/{adw_id}/app/backend/.venv" 2>/dev/null || true
   # Kill Node processes (frontend)
   pkill -f "trees/{adw_id}/app/frontend" 2>/dev/null || true
   sleep 2
   # Force kill any remaining
   pkill -9 -f "trees/{adw_id}" 2>/dev/null || true
   ```

2. **Drop the isolated database**:
   ```bash
   cd adws && python3 scripts/drop_adw_database.py {adw_id}
   ```
   This drops the database `appdb_{adw_id_suffix}`.

3. Check if trees/{adw_id} exists
4. Run `git worktree remove trees/{adw_id}` to remove it
5. Report success or any errors

### Remove all worktrees
If action is "all":
1. First list all worktrees that will be removed
2. **Kill ALL processes from worktrees first** (do this once before the loop):
   ```bash
   # Kill all Python processes from any worktree
   pkill -f "trees/[0-9]*-[a-f0-9]*/app/backend/.venv" 2>/dev/null || true
   # Kill all Node processes from any worktree
   pkill -f "trees/[0-9]*-[a-f0-9]*/app/frontend" 2>/dev/null || true
   # Also kill multiprocessing children explicitly
   pkill -f "multiprocessing.spawn" 2>/dev/null || true
   pkill -f "multiprocessing.resource_tracker" 2>/dev/null || true
   sleep 2
   # Force kill any remaining worktree processes
   pkill -9 -f "trees/[0-9]*-[a-f0-9]*" 2>/dev/null || true
   ```
3. For each worktree under trees/:
   a. Extract the adw_id from the directory name
   b. **Drop the isolated database**:
      ```bash
      cd adws && python3 scripts/drop_adw_database.py {adw_id}
      ```
   c. Run `git worktree remove trees/{adw_id}`
4. Clean up any remaining directories under trees/
5. Run `git worktree prune` to clean up any stale entries

## Report

Report the results of the cleanup operation:
- Number of processes killed (if any were running)
- Number of worktrees removed
- Number of databases dropped
- Any errors encountered (processes, database, or worktree)
- Current status after cleanup