#!/usr/bin/env python3

"""
Browser Tab Cleaner

This script connects to Chrome via the DevTools Protocol to automatically close
unwanted tabs including:
- Empty pages (new tab pages, failed loads)
- Jenkins-related tabs (console logs, completed builds, all Jenkins pages)
- Configurable sites (specified via JSON configuration file)

Before running this script, start Chrome with remote debugging enabled:
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222

Examples:
  python3 browser_tab_cleaner.py                        # Close all matching tabs
  python3 browser_tab_cleaner.py --dry-run              # Show what would be closed without closing
  python3 browser_tab_cleaner.py --jenkins-only         # Only close Jenkins tabs
  python3 browser_tab_cleaner.py --empty-only           # Only close empty tabs
  python3 browser_tab_cleaner.py --configurable-only    # Only close configurable site tabs
  python3 browser_tab_cleaner.py --config my_config.json # Use custom config file

Configuration:
  Create a tab_cleaner_config.json file to specify additional sites to clean.
  The config file supports multiple match types: domain_contains, domain_exact,
  url_contains, and url_regex.
"""

import argparse
import json
import os
import re
import requests
import sys
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple


def _get_chrome_tabs() -> List[Dict]:
    """
    Get list of all open Chrome tabs via DevTools Protocol.

    Return Value(s):
        List[Dict]: List of tab information dictionaries.
    """
    try:
        response = requests.get('http://localhost:9222/json', timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Chrome DevTools. Make sure Chrome is running with --remote-debugging-port=9222")
        print(f"Error details: {e}")
        sys.exit(1)


def _load_config(config_path: Optional[str] = None) -> Dict:
    """
    Load configuration from JSON file.

    Arg(s):
        config_path (Optional[str]): Path to config file. If None, looks for tab_cleaner_config.json in current directory.

    Return Value(s):
        Dict: Configuration data with configurable sites.
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'tab_cleaner_config.json')

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            # Return empty config if file doesn't exist
            return {"configurable_sites": []}
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load config file {config_path}: {e}")
        return {"configurable_sites": []}


def _is_empty_tab(tab: Dict) -> Tuple[bool, str]:
    """
    Check if a tab should be considered 'empty' and closed.

    Arg(s):
        tab (Dict): Tab information from Chrome DevTools.

    Return Value(s):
        Tuple[bool, str]: (should_close, reason)
    """
    url = tab.get('url', '')
    title = tab.get('title', '')

    # New tab pages
    empty_urls = [
        'chrome://newtab/',
        'about:blank',
        'chrome://new-tab-page/',
        'edge://newtab/',
        'about:newtab'
    ]

    for empty_url in empty_urls:
        if url.startswith(empty_url):
            return True, f"New tab page: {url}"

    # Failed loads - common error indicators
    error_indicators = [
        'This site can\'t be reached',
        'Page not found',
        'Server not found',
        'Connection timed out',
        'DNS_PROBE_FINISHED',
        'ERR_',
        'Cannot connect to',
        'Failed to load',
        'Untitled'
    ]

    for indicator in error_indicators:
        if indicator.lower() in title.lower():
            return True, f"Failed load detected: {title}"

    # Check for minimal content pages (very short titles that might indicate errors)
    if len(title.strip()) == 0:
        return True, f"Empty title: {url}"

    return False, ""


def _is_jenkins_tab(tab: Dict) -> Tuple[bool, str]:
    """
    Check if a tab is a Jenkins-related page that should be closed.

    Arg(s):
        tab (Dict): Tab information from Chrome DevTools.

    Return Value(s):
        Tuple[bool, str]: (should_close, reason)
    """
    url = tab.get('url', '')
    title = tab.get('title', '')

    # Jenkins domain patterns
    jenkins_domains = [
        'art-jenkins.apps.',
        'jenkins.',
        'ci.jenkins.io',
        'hudson.',
        'buildbot.'
    ]

    is_jenkins_domain = any(domain in url for domain in jenkins_domains)

    if not is_jenkins_domain:
        return False, ""

    # Console log pages
    console_patterns = [
        '/console',
        '/consoleFull',
        'consoleText',
        '/log'
    ]

    for pattern in console_patterns:
        if pattern in url:
            return True, f"Jenkins console log: {url}"

    # All Jenkins pages (as requested)
    if is_jenkins_domain:
        # Check if it's a completed build by looking for build status in title
        completion_indicators = [
            'SUCCESS',
            'FAILURE',
            'ABORTED',
            'UNSTABLE',
            'COMPLETED'
        ]

        for indicator in completion_indicators:
            if indicator in title.upper():
                return True, f"Completed Jenkins build: {title}"

        # Close all Jenkins pages as requested
        return True, f"Jenkins page: {url}"

    return False, ""


def _is_configurable_site_tab(tab: Dict, config: Dict) -> Tuple[bool, str]:
    """
    Check if a tab matches any configured site patterns and should be closed.

    Arg(s):
        tab (Dict): Tab information from Chrome DevTools.
        config (Dict): Configuration with configurable sites.

    Return Value(s):
        Tuple[bool, str]: (should_close, reason)
    """
    url = tab.get('url', '')

    for site_config in config.get('configurable_sites', []):
        # Skip disabled sites
        if not site_config.get('enabled', True):
            continue

        name = site_config.get('name', 'Unknown site')
        patterns = site_config.get('patterns', [])
        match_type = site_config.get('match_type', 'domain_contains')

        for pattern in patterns:
            should_close = False

            if match_type == 'domain_contains':
                if pattern in url:
                    should_close = True
            elif match_type == 'domain_exact':
                # Extract domain from URL
                try:
                    parsed_url = urllib.parse.urlparse(url)
                    domain = parsed_url.netloc.lower()
                    if domain == pattern.lower():
                        should_close = True
                except:
                    pass
            elif match_type == 'url_contains':
                if pattern in url:
                    should_close = True
            elif match_type == 'url_regex':
                try:
                    if re.search(pattern, url):
                        should_close = True
                except re.error:
                    # Skip invalid regex patterns
                    pass

            if should_close:
                return True, f"{name}: {url}"

    return False, ""


def _close_tab(tab: Dict, dry_run: bool = False) -> bool:
    """
    Close a specific Chrome tab.

    Arg(s):
        tab (Dict): Tab information from Chrome DevTools.
        dry_run (bool): If True, don't actually close the tab.

    Return Value(s):
        bool: True if tab was closed (or would be closed in dry run).
    """
    tab_id = tab.get('id')
    if not tab_id:
        return False

    if dry_run:
        return True

    try:
        close_url = f'http://localhost:9222/json/close/{tab_id}'
        response = requests.get(close_url, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def clean_chrome_tabs(jenkins_only: bool = False, empty_only: bool = False, configurable_only: bool = False,
                     dry_run: bool = False, config_path: Optional[str] = None) -> None:
    """
    Main function to clean Chrome tabs based on specified criteria.

    Arg(s):
        jenkins_only (bool): Only clean Jenkins tabs.
        empty_only (bool): Only clean empty tabs.
        configurable_only (bool): Only clean configurable site tabs.
        dry_run (bool): Show what would be closed without actually closing.
        config_path (Optional[str]): Path to configuration file.
    """
    print("Getting Chrome tabs...")
    tabs = _get_chrome_tabs()

    if not tabs:
        print("No tabs found.")
        return

    print(f"Found {len(tabs)} total tabs.")

    # Load configuration for configurable sites
    config = _load_config(config_path)
    configurable_sites_count = len([site for site in config.get('configurable_sites', []) if site.get('enabled', True)])
    if configurable_sites_count > 0:
        print(f"Loaded configuration with {configurable_sites_count} enabled configurable sites.")

    tabs_to_close = []

    for tab in tabs:
        url = tab.get('url', 'Unknown')
        title = tab.get('title', 'Unknown')

        # Skip Chrome extension and internal pages
        if url.startswith('chrome-extension://') or url.startswith('chrome://'):
            if not url.startswith('chrome://newtab'):  # Still allow closing new tab pages
                continue

        should_close = False
        reason = ""

        if not jenkins_only and not configurable_only:
            is_empty, empty_reason = _is_empty_tab(tab)
            if is_empty:
                should_close = True
                reason = empty_reason

        if not empty_only and not configurable_only and not should_close:
            is_jenkins, jenkins_reason = _is_jenkins_tab(tab)
            if is_jenkins:
                should_close = True
                reason = jenkins_reason

        if not empty_only and not jenkins_only and not should_close:
            is_configurable, configurable_reason = _is_configurable_site_tab(tab, config)
            if is_configurable:
                should_close = True
                reason = configurable_reason

        if should_close:
            tabs_to_close.append((tab, reason))

    if not tabs_to_close:
        print("No tabs found matching the cleanup criteria.")
        return

    print(f"\n{'Would close' if dry_run else 'Closing'} {len(tabs_to_close)} tabs:")
    print("-" * 80)

    closed_count = 0
    for tab, reason in tabs_to_close:
        url = tab.get('url', 'Unknown')
        title = tab.get('title', 'Unknown')

        # Truncate long titles/URLs for display
        display_title = title[:60] + "..." if len(title) > 60 else title
        display_url = url[:80] + "..." if len(url) > 80 else url

        print(f"Title: {display_title}")
        print(f"URL:   {display_url}")
        print(f"Reason: {reason}")

        if _close_tab(tab, dry_run):
            closed_count += 1
            if not dry_run:
                time.sleep(0.1)  # Brief pause between closings

        print("-" * 80)

    action = "would be closed" if dry_run else "closed"
    print(f"\nSummary: {closed_count} tabs {action}.")

    if dry_run:
        print("\nTo actually close these tabs, run the script without --dry-run")


def main():
    """
    Main entry point for the browser tab cleaner script.
    """
    parser = argparse.ArgumentParser(
        description="Clean unwanted browser tabs (empty pages, Jenkins tabs, and configurable sites)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Close all matching tabs
  %(prog)s --dry-run                 # Show what would be closed
  %(prog)s --jenkins-only            # Only close Jenkins tabs
  %(prog)s --empty-only              # Only close empty tabs
  %(prog)s --configurable-only       # Only close configurable site tabs
  %(prog)s --config config.json      # Use custom config file

Before running, start Chrome with remote debugging:
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222

Configuration:
  Create a tab_cleaner_config.json file to specify additional sites to clean.
  See the example config file for format and options.
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what tabs would be closed without actually closing them'
    )

    parser.add_argument(
        '--jenkins-only',
        action='store_true',
        help='Only close Jenkins-related tabs'
    )

    parser.add_argument(
        '--empty-only',
        action='store_true',
        help='Only close empty/failed pages'
    )

    parser.add_argument(
        '--configurable-only',
        action='store_true',
        help='Only close tabs from configurable sites (specified in config file)'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file (default: tab_cleaner_config.json in script directory)'
    )

    args = parser.parse_args()

    # Validate mutually exclusive options
    exclusive_options = [args.jenkins_only, args.empty_only, args.configurable_only]
    if sum(exclusive_options) > 1:
        print("Error: Can only specify one of --jenkins-only, --empty-only, or --configurable-only")
        sys.exit(1)

    try:
        clean_chrome_tabs(
            jenkins_only=args.jenkins_only,
            empty_only=args.empty_only,
            configurable_only=args.configurable_only,
            dry_run=args.dry_run,
            config_path=args.config
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)


if __name__ == '__main__':
    main()