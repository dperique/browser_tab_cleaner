# Browser Tab Closer

Automatically close unwanted browser tabs including empty pages and Jenkins-related tabs.

**Currently Supported:** Google Chrome only (via DevTools Protocol)

## Current Features

### Supported Browsers
- ✅ Google Chrome (with DevTools Protocol)
- ❌ Firefox, Safari, Edge (not yet implemented)

### Supported Operating Systems
- ✅ macOS
- ❌ Windows, Linux (paths need updating)

## What It Closes

**Empty Pages:**
- New tab pages (`chrome://newtab/`, `about:blank`)
- Failed loads (DNS errors, connection timeouts, etc.)
- Pages with empty titles

**Jenkins Pages:**
- Console log pages (`/console`, `/consoleFull`)
- Completed builds (SUCCESS, FAILURE, ABORTED)
- All Jenkins domain pages (`art-jenkins.apps.*`, etc.)

## Setup

### 1. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 2. Start Chrome with Debugging

**Option A: Quick Restart (Recommended)**
1. Quit Chrome completely (Cmd+Q)
2. Start with debugging:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
   ```

**Option B: Create an Alias**
Add to your `~/.zshrc`:
```bash
alias chrome-debug='/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222'
```
Then just run: `chrome-debug`

**Option C: Separate Instance (Keep Current Chrome)**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

## Usage

### Preview First (Recommended)
```bash
python3 browser_tab_cleaner.py --dry-run
```
Shows exactly which tabs would be closed without actually closing them.

### Close All Matching Tabs
```bash
python3 browser_tab_cleaner.py
```

### Close Only Specific Types
```bash
# Only Jenkins tabs
python3 browser_tab_cleaner.py --jenkins-only

# Only empty/failed pages
python3 browser_tab_cleaner.py --empty-only
```

## Typical Workflow

1. Start Chrome with debugging enabled
2. Use `--dry-run` to see what would be closed
3. Review the list to make sure nothing important gets closed
4. Run without `--dry-run` to actually close the tabs

## Example Output

```
Found 25 total tabs.

Would close 8 tabs:
--------------------------------------------------------------------------------
Title: New Tab
URL:   chrome://newtab/
Reason: New tab page: chrome://newtab/
--------------------------------------------------------------------------------
Title: Console Output [Jenkins]
URL:   https://art-jenkins.apps.prod-stable-spoke1-dc-iad2.itup.redhat.com/job/my-job/123/console
Reason: Jenkins console log: https://art-jenkins.apps...
--------------------------------------------------------------------------------
```

## Future Improvements

- Support for Firefox (via WebDriver or native messaging)
- Support for Safari (via AppleScript)
- Support for Edge (via DevTools Protocol)
- Windows/Linux compatibility
- GUI interface
- Configurable rules for tab detection
- Scheduled/automatic cleanup