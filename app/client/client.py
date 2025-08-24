import logging
import os
import datetime
import urllib
import io
import csv
from flask_cors import CORS
from flask import Flask, request, jsonify, send_file, abort, make_response, send_from_directory

from app.helpers.config import APP_NAME, LOCAL_RETENTION_DAYS, TIMELINE_LIMIT, CLIENT_PORT
from app.logger import configure_client_logger
from app.client.helpers import row_to_record, fetch_image_rows, downsample, resolve_serving_path, candidates_from_path_string


APP = Flask(APP_NAME, static_folder='./static/')
CORS(APP)


@APP.route('/')
def index():
    return send_from_directory("templates", "index.html")


@APP.route('/api/config')
def api_config():
    """
    Return small config object consumed by the front-end.
    Keeps UI in sync with the recorder retention config.
    """
    try:
        return jsonify({
            "local_retention_days": LOCAL_RETENTION_DAYS
        })
    except Exception:
        # graceful fallback
        return jsonify({"local_retention_days": 7})


@APP.route('/api/search')
def api_search():
    win_title = request.args.get('win_title', type=str)
    win_app = request.args.get('win_app', type=str)
    start = request.args.get('start', type=str)
    end = request.args.get('end', type=str)
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=20, type=int)

    page = max(1, page)
    page_size = max(1, min(200, page_size))

    # fetch all rows matching win_title / win_app filters
    rows = fetch_image_rows(win_title, win_app, start=start, end=end)

    # parse start / end filters
    start_dt = None
    end_dt = None
    try:
        if start:
            start_dt = datetime.datetime.fromisoformat(start)
        if end:
            end_dt = datetime.datetime.fromisoformat(end)
    except Exception:
        pass

    # convert rows to dicts and apply start/end filtering
    filtered = []
    for r in rows:
        rec = row_to_record(r)
        ts = rec.get('timestamp')
        ts_dt = None
        if ts:
            try:
                ts_dt = datetime.datetime.fromisoformat(ts)
            except Exception:
                pass
        if start_dt and ts_dt and ts_dt < start_dt:
            continue
        if end_dt and ts_dt and ts_dt > end_dt:
            continue
        filtered.append(rec)

    # SORT descending by timestamp (latest first)
    def ts_key(r):
        ts = r.get('timestamp')
        try:
            return datetime.datetime.fromisoformat(ts)
        except Exception:
            return datetime.datetime.min  # fallback for missing/invalid timestamps

    filtered.sort(key=ts_key, reverse=True)

    # pagination
    total = len(filtered)
    start_idx = (page-1) * page_size
    end_idx = start_idx + page_size
    page_rows = filtered[start_idx:end_idx]

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'rows': page_rows
    })


@APP.route('/api/timeline')
def api_timeline():
    win_title = request.args.get('win_title', type=str)
    win_app = request.args.get('win_app', type=str)
    start = request.args.get('start', type=str)
    end = request.args.get('end', type=str)

    rows = fetch_image_rows(win_title, win_app, start=start, end=end)
    items = []
    start_dt = None
    end_dt = None
    try:
        if start:
            start_dt = datetime.datetime.fromisoformat(start)
        if end:
            end_dt = datetime.datetime.fromisoformat(end)
    except Exception:
        pass

    for r in rows:
        rec = row_to_record(r)
        if not rec.get('ts_ms'):
            continue
        ts_dt = datetime.datetime.fromisoformat(rec['timestamp'])
        if start_dt and ts_dt < start_dt:
            continue
        if end_dt and ts_dt > end_dt:
            continue
        items.append({'timestamp': rec['timestamp'], 'ts_ms': rec['ts_ms'], 'local_path': rec['local_path'], 'backup_path': rec['backup_path'], 'win_title': rec.get(
            'win_title'), 'win_app': rec.get('win_app')})

    items = sorted(items, key=lambda x: x['ts_ms'])
    items = downsample(items, TIMELINE_LIMIT)
    return jsonify({'total': len(items), 'items': items})


@APP.route('/api/image_at')
def api_image_at():
    # returns single image record latest <= provided ts (ts as ISO or epoch ms)
    ts_in = request.args.get('ts', type=str)
    if not ts_in:
        return jsonify({'error': 'ts param required'}), 400
    # accept epoch ms or ISO
    try:
        if ts_in.isdigit():
            ts_dt = datetime.datetime.fromtimestamp(int(ts_in)/1000)
        else:
            ts_dt = datetime.datetime.fromisoformat(ts_in)
    except Exception:
        return jsonify({'error': 'invalid ts format'}), 400

    win_title = request.args.get('win_title', type=str)
    win_app = request.args.get('win_app', type=str)

    rows = fetch_image_rows(win_title, win_app, start=None, end=None)
    best = None
    best_ts = None
    for r in rows:
        rec = row_to_record(r)
        if not rec.get('timestamp'):
            continue
        try:
            t = datetime.datetime.fromisoformat(rec['timestamp'])
            if t <= ts_dt and (best_ts is None or t > best_ts):
                best = rec
                best_ts = t
        except Exception:
            continue

    if not best:
        return jsonify({'found': False}), 404
    return jsonify({'found': True, 'record': best})


@APP.route('/api/thumbnail')
def api_thumbnail():
    path = request.args.get('path', type=str)
    if not path:
        abort(400)
    path = urllib.parse.unquote_plus(path)

    # If path looks like a DB-stored value (may be relative or absolute),
    # attempt to resolve via candidates and retention policy.
    # If a direct match exists on filesystem, serve that.
    # Otherwise try to map to backup location.
    # We attempt to read a DB record if the path is actually a DB 'path' value (id could be passed),
    # but most callers pass the stored path string — so we best-effort resolve it.
    # Try quick-resolve by creating a pseudo-record with the path in local_path.
    rec = {'local_path': path, 'backup_path': ''}
    resolved = resolve_serving_path(rec)
    if not resolved:
        # fallback: attempt mapping via safe_image_path-like behavior
        resolved_local, resolved_backup = candidates_from_path_string(path)
        resolved = resolved_local or resolved_backup

    if not resolved or not os.path.exists(resolved):
        abort(404)
    return send_file(resolved)


@APP.route('/api/open')
def api_open():
    path = request.args.get('path', type=str)
    if not path:
        abort(400)
    path = urllib.parse.unquote_plus(path)

    rec = {'local_path': path, 'backup_path': ''}
    resolved = resolve_serving_path(rec)
    if not resolved:
        resolved_local, resolved_backup = candidates_from_path_string(path)
        resolved = resolved_local or resolved_backup

    if not resolved or not os.path.exists(resolved):
        abort(404)
    return send_file(resolved)


@APP.route('/api/export')
def api_export():
    win_title = request.args.get('win_title', type=str)
    win_app = request.args.get('win_app', type=str)
    start = request.args.get('start', type=str)
    end = request.args.get('end', type=str)

    rows = fetch_image_rows(win_title, win_app, start=start, end=end)
    filtered = []
    start_dt = None
    end_dt = None
    try:
        if start:
            start_dt = datetime.datetime.fromisoformat(start)
        if end:
            end_dt = datetime.datetime.fromisoformat(end)
    except Exception:
        pass

    for r in rows:
        rec = row_to_record(r)
        if not rec.get('ts_ms'):
            continue
        ts_dt = datetime.datetime.fromisoformat(rec['timestamp'])
        if start_dt and ts_dt < start_dt:
            continue
        if end_dt and ts_dt > end_dt:
            continue
        filtered.append(rec)

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['day', 'session', 'timestamp',
                'local_path', 'backup_path', 'win_title', 'win_app'])
    for r in filtered:
        cw.writerow([r.get('day'), r.get('session'), r.get(
            'timestamp'), r.get('local_path'), r.get('backup_path'), r.get('win_title'), r.get('win_app')])
    output = make_response(si.getvalue())
    output.headers['Content-Disposition'] = 'attachment; filename=recall-export.csv'
    output.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return output


def run_flask_app():
    # Redirect Flask's internal logger to your logger
    client_logger = configure_client_logger()
    APP.logger.handlers = client_logger.handlers
    APP.logger.setLevel(client_logger.level)

    # Replace Werkzeug's default handler with client logger
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = []  # remove default console handlers
    werkzeug_logger.propagate = False  # prevent double logging

    # Add your client logger handler to Werkzeug
    for handler in client_logger.handlers:
        werkzeug_logger.addHandler(handler)

    werkzeug_logger.setLevel(logging.INFO)

    APP.run(port=CLIENT_PORT, debug=False, use_reloader=False)
