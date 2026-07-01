"""
UpdateData.py — Quickly update data.json + regenerate dashboard.html
No need to regenerate full HTML reports; only calls TestRail API for tracked metrics.

Usage (exe):
  UpdateData.exe <email> <password> <run_id1> [run_id2 run_id3 ...]

Interactive (no args):
  UpdateData.exe
  -> prompts for email, password, run IDs
"""

from DrissionPage import SessionPage
from datetime import date as _date
import json
import re
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

TESTRAIL = 'https://synasdd.testrail.net/index.php?/api/v2/'

STATUS_INFO = {
    1: 'Passed',  5: 'Failed',   3: 'Untested', 4: 'Retest',
    2: 'Blocked', 6: 'Aborted',  7: 'Partial_Pass', 8: 'Partial_Fail',
    9: 'Conditional_Pass', 10: 'Not_Required', 11: 'NOT_Run', 12: 'Unknown'
}


def _extract_value_unit(html, unit_hint=''):
    text = ' '.join(re.sub(r'<[^>]+>', '', str(html)).split())
    if unit_hint:
        m = re.search(r'(\d+\.?\d*)\s*' + re.escape(unit_hint), text, re.IGNORECASE)
        if m:
            return float(m.group(1)), unit_hint
    m = re.search(r'(\d+\.?\d*)\s*([a-zA-Z%]+)', text)
    if m:
        return float(m.group(1)), m.group(2)
    return None, ''


def _parse_run_desc(desc):
    info = {}
    if not desc:
        return info
    text = re.sub(r'<[^>]+>', '', desc)
    for pattern, key in [
        (r'(HQA-\d+)',        'jira'),
        (r'(TM-[A-Z0-9-]+)', 'tm_number'),
        (r'(PR\d+)',          'pr_number'),
        (r'\((v[\d.]+)\)',    'fw_version'),
    ]:
        m = re.search(pattern, text)
        if m:
            info[key] = m.group(1)
    m = re.search(r'\(([A-Z]+\d+)_([^_]+)_([^\s(]+)', text)
    if m:
        info['asic']     = m.group(1)
        info['protocol'] = m.group(2)
        info['model']    = m.group(3)
    return info


def api_get(page, endpoint):
    """GET one TestRail API endpoint, return parsed JSON (dict or list) or None on failure."""
    try:
        page.get(TESTRAIL + endpoint)
        result = page.json
        return result
    except Exception as e:
        print(f'    [api_get] ERROR on {endpoint}: {e}')
        return None


def fetch_all_tests(page, run_id):
    """Fetch all tests for a run (handles pagination)."""
    all_tests = []
    offset = 0
    page_num = 0
    while True:
        page_num += 1
        url = f'get_tests/{run_id}' if offset == 0 else f'get_tests/{run_id}/3&offset={offset}'
        resp = api_get(page, url)

        if resp is None:
            print(f'    [fetch_all_tests] got None response on page {page_num}, stopping.')
            break
        if isinstance(resp, dict) and 'error' in resp:
            print(f'    [fetch_all_tests] API error: {resp["error"]}')
            break
        if not isinstance(resp, dict):
            print(f'    [fetch_all_tests] unexpected response type: {type(resp).__name__}')
            break

        tests = resp.get('tests', [])
        all_tests.extend(tests)
        size  = resp.get('size', 0)
        limit = resp.get('limit', 250)
        if size < limit:
            break
        offset += size
    return all_tests


def fetch_all_results(page, run_id):
    """Fetch all results for a run using get_results_for_run (same as ReportGenerator).
    Returns a dict: test_id -> comment (latest comment wins).
    """
    all_results = []
    offset = 0
    page_num = 0
    while True:
        page_num += 1
        url = f'get_results_for_run/{run_id}' if offset == 0 else f'get_results_for_run/{run_id}/3&offset={offset}'
        resp = api_get(page, url)

        if resp is None:
            print(f'    [fetch_all_results] None response on page {page_num}, stopping.')
            break
        if isinstance(resp, dict) and 'error' in resp:
            print(f'    [fetch_all_results] API error: {resp["error"]}')
            break
        if not isinstance(resp, dict):
            break

        results = resp.get('results', [])
        all_results.extend(results)
        size  = resp.get('size', 0)
        limit = resp.get('limit', 250)
        if size < limit:
            break
        offset += size

    # Build test_id -> latest comment mapping (results are newest-first per test_id)
    comment_map = {}
    for r in all_results:
        tid     = r.get('test_id')
        comment = r.get('comment') or ''
        if tid not in comment_map:  # keep first (newest) result per test_id
            comment_map[tid] = comment
    return comment_map


def process_run(page, run_id, tracked_case_ids, cfg_metrics, existing_run=None):
    """
    Fetch a single run's data from TestRail and return a run dict.
    Returns None if the run cannot be processed (API error, etc.).
    existing_run: the existing entry in data.json for this run_id (if any), used as fallback for metadata.
    """
    print(f'\n  Processing run {run_id}...')

    # --- Run metadata ---
    run_info = api_get(page, f'get_run/{run_id}')
    if run_info is None:
        print('  ERROR: failed to fetch run info (API returned None)')
        return None
    if isinstance(run_info, dict) and 'error' in run_info:
        print(f'  ERROR: {run_info["error"]}')
        return None

    description = run_info.get('description', '') or ''
    meta = _parse_run_desc(description)

    # Merge with existing entry's metadata if new extraction is missing fields
    if existing_run:
        for field in ('tm_number', 'fw_version', 'pr_number', 'jira', 'asic', 'protocol', 'model'):
            if not meta.get(field) and existing_run.get(field):
                meta[field] = existing_run[field]

    # For NEW runs (not in data.json), require tm_number
    is_new_run = (existing_run is None)
    if is_new_run and not meta.get('tm_number'):
        print(f'  SKIPPED: could not extract TM number from description.')
        print(f'    Description: {description[:200]}')
        print('    Hint: description must contain a pattern like "TM-P1234-001"')
        return None

    print(f'    FW={meta.get("fw_version","?")}  TM={meta.get("tm_number","?")}  PR={meta.get("pr_number","?")}')

    # --- All tests ---
    all_tests = fetch_all_tests(page, run_id)
    print(f'    Total tests fetched: {len(all_tests)}')

    # Status counts
    status_amount = {name: 0 for name in STATUS_INFO.values()}
    for t in all_tests:
        sid  = t.get('status_id', 12)
        name = STATUS_INFO.get(sid, 'Unknown')
        status_amount[name] = status_amount.get(name, 0) + 1

    # Show which tracked cases are found
    found_cids = []
    for t in all_tests:
        raw_cid = t.get('case_id')
        if raw_cid is None:
            continue
        cid = int(raw_cid) if not isinstance(raw_cid, int) else raw_cid
        if cid in tracked_case_ids:
            found_cids.append(cid)
    if tracked_case_ids:
        missing = [c for c in tracked_case_ids if c not in found_cids]
        if missing:
            print(f'    WARNING: tracked case_ids not found in this run: {missing}')
        else:
            print(f'    Tracked cases found: {found_cids}')

    # --- Extract tracked metric values ---
    comment_map = fetch_all_results(page, run_id)
    tracked_results = []
    for t in all_tests:
        raw_cid = t.get('case_id')
        if raw_cid is None:
            continue
        cid = int(raw_cid) if not isinstance(raw_cid, int) else raw_cid
        if cid not in tracked_case_ids:
            continue

        test_id = t['id']
        note_html = comment_map.get(test_id, '')

        metric_def = next((md for md in cfg_metrics if md.get('case_id') == cid), {})
        unit_hint  = metric_def.get('unit', '')
        value, unit = _extract_value_unit(note_html, unit_hint)

        sid      = t.get('status_id', 12)
        status_s = STATUS_INFO.get(sid, 'Unknown')

        raw_text = re.sub(r'<[^>]+>', '', note_html).strip()
        tracked_results.append({
            'case_id':     cid,
            'title':       t.get('title', ''),
            'status':      status_s.lower(),
            'value':       value,
            'unit':        unit,
            'raw_comment': raw_text
        })
        print(f'    Case {cid}: value={value} {unit}  status={status_s}')
        if value is None and note_html:
            print(f'      (raw comment: {raw_text[:80]})')

    return {
        'run_id':      str(run_id),
        'fw_version':  meta.get('fw_version', ''),
        'pr_number':   meta.get('pr_number', ''),
        'tm_number':   meta.get('tm_number', ''),
        'jira':        meta.get('jira', ''),
        'asic':        meta.get('asic', ''),
        'protocol':    meta.get('protocol', ''),
        'model':       meta.get('model', ''),
        'date':        str(_date.today()),
        'tester':      '',
        'total_tests': sum(status_amount.values()),
        'passed':      status_amount.get('Passed', 0),
        'failed':      status_amount.get('Failed', 0),
        'blocked':     status_amount.get('Blocked', 0),
        'results':     tracked_results
    }


def main():
    if len(sys.argv) >= 4:
        email    = sys.argv[1]
        password = sys.argv[2]
        run_ids  = [int(x) for x in sys.argv[3:]]
    elif len(sys.argv) == 3:
        email    = sys.argv[1]
        password = sys.argv[2]
        ids_str  = input('Run IDs (space-separated): ').strip()
        run_ids  = [int(x) for x in ids_str.split()]
    else:
        print('=== UpdateData — Update data.json + dashboard.html ===')
        email    = input('TestRail Email: ').strip()
        password = input('Password: ').strip()
        ids_str  = input('Run IDs (space-separated): ').strip()
        run_ids  = [int(x) for x in ids_str.split()]

    if not run_ids:
        print('No run IDs provided. Exit.')
        return

    # Locate config.json
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(base_path, 'config.json')
    if not os.path.exists(config_path):
        print(f'config.json not found at: {config_path}')
        return

    with open(config_path, encoding='utf8') as f:
        config = json.load(f)

    shared_folder    = config.get('shared_folder', {})
    # Ensure tracked_case_ids are integers
    tracked_case_ids = [int(x) for x in config.get('tracked_case_ids', [])]
    cfg_metrics      = config.get('tracked_metrics', [])
    dashboard_dir    = shared_folder.get('dashboard', '')

    if not dashboard_dir:
        print('ERROR: shared_folder.dashboard not configured in config.json')
        return

    # Login
    print(f'\nLogging in as {email}...')
    page = SessionPage(timeout=15)
    page.post('https://synasdd.testrail.net/index.php?/auth/login/', data={'name': email, 'password': password})

    # Quick auth check via get_run of first run_id
    check = api_get(page, f'get_run/{run_ids[0]}')
    if check is None or (isinstance(check, dict) and 'error' in check):
        err = check.get('error', 'no response') if isinstance(check, dict) else 'no response'
        print(f'Authentication failed: {err}')
        return
    print('Login OK.')

    # Load existing data.json
    os.makedirs(dashboard_dir, exist_ok=True)
    data_json_path = os.path.join(dashboard_dir, 'data.json')
    if os.path.exists(data_json_path):
        # utf-8-sig handles files with or without BOM
        with open(data_json_path, encoding='utf-8-sig') as f:
            data_json = json.load(f)
        print(f'Loaded existing data.json ({len(data_json.get("runs", []))} runs)')
    else:
        data_json = {'_schema_version': '1.0', 'project': {}, 'tracked_metrics': [], 'runs': []}
        print('Creating new data.json')

    if cfg_metrics:
        data_json['tracked_metrics'] = cfg_metrics

    added = updated = skipped = 0

    for run_id in run_ids:
        # Find existing entry for this run_id (used as metadata fallback)
        existing_idx = next(
            (i for i, r in enumerate(data_json['runs']) if str(r.get('run_id')) == str(run_id)),
            None
        )
        existing_run = data_json['runs'][existing_idx] if existing_idx is not None else None

        new_run = process_run(page, run_id, tracked_case_ids, cfg_metrics, existing_run)

        if new_run is None:
            skipped += 1
            continue

        if existing_idx is not None:
            data_json['runs'][existing_idx] = new_run
            print(f'  -> Updated run {run_id} in data.json')
            updated += 1
        else:
            data_json['runs'].append(new_run)
            print(f'  -> Added run {run_id} to data.json')
            added += 1

    print(f'\nSummary: added={added}, updated={updated}, skipped={skipped}')

    if added + updated == 0:
        print('Nothing changed. data.json and dashboard.html NOT updated.')
        return

    # Save data.json (no BOM)
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(data_json, f, ensure_ascii=False, indent=2)
    print(f'data.json saved -> {data_json_path}')

    # Regenerate dashboard.html
    template_src = os.path.join(base_path, 'templates', 'dashboard.html')
    if os.path.exists(template_src):
        with open(template_src, encoding='utf8') as f:
            dash_html = f.read()
        injected = dash_html.replace('/* __INJECT__ */ null', json.dumps(data_json, ensure_ascii=False), 1)
        if injected == dash_html:
            print('WARNING: injection placeholder not found in template!')
        else:
            out_path = os.path.join(dashboard_dir, 'dashboard.html')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(injected)
            print(f'dashboard.html updated -> {dashboard_dir}')
    else:
        print(f'WARNING: dashboard template not found at {template_src}')

    print('\nDone!')


if __name__ == '__main__':
    main()
