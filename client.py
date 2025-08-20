import threading
import webbrowser
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import sys

import urllib.parse
import io
import csv
import datetime
from pathlib import Path
import os
import sqlite3
import yaml
from flask_cors import CORS
from flask import Flask, request, jsonify, send_file, abort, make_response, send_from_directory

APP = Flask(__name__, static_folder='.')
CORS(APP)


# Load the ocnfiguration from a YAML file if it exists
with open(".config.yml", "r") as f:
    cfg = yaml.safe_load(f)

# --- CONFIG ---
# <-- update this to your recorder DB file
DB_PATH = Path(cfg["paths"]["db_path"])
# <-- update to your IMAGES_DIR (same root used by recorder)
IMAGES_BASE = Path(cfg["paths"]["images_dir"])
# max number of points returned; server will downsample if exceeded
TIMELINE_LIMIT = cfg["client"]["timeline_limit"]
PORT = cfg["client"]["port"]

# --- Helpers ---


def db_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Parse timestamp from filename. Recorder uses SCREENSHOT_dd_mm_YYYY_H_M_S.webp


def parse_timestamp_from_path(path_str):
    try:
        b = os.path.basename(path_str)
        parts = b.split('_')
        if len(parts) >= 7:
            dd = parts[1]
            mm = parts[2]
            yyyy = parts[3]
            hh = parts[4]
            mi = parts[5]
            ss_and_ext = parts[6]
            ss = ss_and_ext.split('.')[0]
            dt = datetime.datetime(int(yyyy), int(
                mm), int(dd), int(hh), int(mi), int(ss))
            return dt
    except Exception:
        pass
    return None

# Safe path join to images base


def safe_image_path(p):
    p = os.path.normpath(p)
    try:
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = (Path(IMAGES_BASE) / p)
        candidate = candidate.resolve()
        base = Path(IMAGES_BASE).resolve()
        if base in candidate.parents or candidate == base:
            return str(candidate)
    except Exception:
        pass
    return None

# Generic fetch rows with optional filters


def fetch_image_rows(win_title=None, win_app=None):
    conn = db_conn()
    cur = conn.cursor()
    q = "SELECT id, day, session, path, win_title, win_app FROM images WHERE 1=1"
    params = []
    if win_title:
        q += " AND win_title LIKE ?"
        params.append(f"%{win_title}%")
    if win_app:
        q += " AND win_app LIKE ?"
        params.append(f"%{win_app}%")
    q += " ORDER BY day DESC"
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return rows

# Convert DB row into record with parsed timestamp


def row_to_record(r):
    row = dict(r)
    path = row.get('path')
    ts = parse_timestamp_from_path(path)
    if ts is None:
        try:
            day = row.get('day')
            sess = row.get('session')
            if day and sess and '-' in sess:
                hh = int(sess.split('-')[0][:2])
                mm = int(sess.split('-')[0][2:])
                ts = datetime.datetime.fromisoformat(
                    day) + datetime.timedelta(hours=hh, minutes=mm)
        except Exception:
            ts = None
    row['timestamp'] = ts.isoformat() if ts else None
    row['ts_ms'] = int(ts.timestamp() * 1000) if ts else None
    return row

# Downsample list to roughly `limit` points by uniform sampling


def downsample(items, limit):
    if len(items) <= limit:
        return items
    step = max(1, int(len(items) / limit))
    sampled = [items[i] for i in range(0, len(items), step)]
    # ensure last item is included
    if sampled[-1] != items[-1]:
        sampled.append(items[-1])
    return sampled

# --- API ---


@APP.route('/')
def index():
    return send_from_directory('client', 'index.html')


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
    rows = fetch_image_rows(win_title, win_app)

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

    rows = fetch_image_rows(win_title, win_app)
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
        items.append({'timestamp': rec['timestamp'], 'ts_ms': rec['ts_ms'], 'path': rec['path'], 'win_title': rec.get(
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

    rows = fetch_image_rows(win_title, win_app)
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
    safe = safe_image_path(path)
    if not safe or not os.path.exists(safe):
        abort(404)
    return send_file(safe)


@APP.route('/api/open')
def api_open():
    path = request.args.get('path', type=str)
    if not path:
        abort(400)
    path = urllib.parse.unquote_plus(path)
    safe = safe_image_path(path)
    if not safe or not os.path.exists(safe):
        abort(404)
    return send_file(safe)


@APP.route('/api/export')
def api_export():
    win_title = request.args.get('win_title', type=str)
    win_app = request.args.get('win_app', type=str)
    start = request.args.get('start', type=str)
    end = request.args.get('end', type=str)

    rows = fetch_image_rows(win_title, win_app)
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
                'path', 'win_title', 'win_app'])
    for r in filtered:
        cw.writerow([r.get('day'), r.get('session'), r.get(
            'timestamp'), r.get('path'), r.get('win_title'), r.get('win_app')])
    output = make_response(si.getvalue())
    output.headers['Content-Disposition'] = 'attachment; filename=recall-export.csv'
    output.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return output


def run_flask():
    APP.run(port=PORT, debug=False, use_reloader=False)


def create_tray_image():
    img = Image.open(os.path.join("__assets__", "icon-tray.png"))
    img = img.convert("RGBA")
    return img


def open_browser(icon, item):
    webbrowser.open(f'http://127.0.0.1:{PORT}/')


def exit_app(icon, item):
    icon.stop()
    sys.exit(0)


menu = Menu(
    MenuItem('Open Browser', open_browser),
    MenuItem('Exit', exit_app)
)

icon = Icon("Shan's Memory Recorder - Client",
            create_tray_image(), "Shan's Memory Recorder - Client", menu)

if __name__ == '__main__':
    # Run Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start the tray icon
    icon.run()
