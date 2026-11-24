from flask import Flask, send_from_directory, abort, render_template_string
import os
from datetime import datetime

app = Flask(__name__)
DATA_DIR = os.environ.get("OUTDIR", "/data")
LATEST_NAME = "aladin_adriacenter_latest.grb"
MARINE_LATEST_NAME = "copernicus_adriacenter_latest.grb"
PREFIXES = ("aladin_adriacenter_", "copernicus_adriacenter_")
LATEST_NAMES = (LATEST_NAME, MARINE_LATEST_NAME)

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ALADIN GRIB Files</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #333; }
        .latest { background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .latest a { font-size: 1.2em; font-weight: bold; color: #2e7d32; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f5f5f5; font-weight: bold; }
        tr:hover { background-color: #f9f9f9; }
        a { color: #1976d2; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .timestamp { font-family: monospace; }
        .size { text-align: right; }
    </style>
</head>
<body>
    <h1>ALADIN Adria Center GRIB Files</h1>
    
    <div class="latest">
        <strong>Latest:</strong>
        {% for name, exists, stamp in latest %}
            <div>
            {% if exists %}
                <a href="/{{ name }}">{{ name }}</a>
                {% if stamp %}<span class="timestamp">({{ stamp }})</span>{% endif %}
            {% else %}
                {{ name }}: <span style="color: #d32f2f;">Not available yet</span>
            {% endif %}
            </div>
        {% endfor %}
    </div>
    
    <h2>All Available Files</h2>
    {% if files %}
        <table>
            <tr>
                <th>Filename</th>
                <th>Timestamp</th>
                <th>Modified</th>
                <th class="size">Size</th>
            </tr>
            {% for file in files %}
            <tr>
                <td><a href="/files/{{ file.name }}">{{ file.name }}</a></td>
                <td class="timestamp">{{ file.timestamp }}</td>
                <td>{{ file.modified }}</td>
                <td class="size">{{ file.size }}</td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p>No files available yet.</p>
    {% endif %}
</body>
</html>
"""

def format_size(bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} TB"

def parse_timestamp(filename):
    """Extract timestamp from filename"""
    try:
        # Format: aladin_adriacenter_YYYYMMDDHH.grb or copernicus_adriacenter_YYYYMMDD00.grb
        parts = filename.split('_')
        if len(parts) >= 3:
            ts = parts[2].replace('.grb', '')
            if len(ts) == 10 and ts.isdigit():
                # Format as YYYY-MM-DD HH:00
                return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:00"
    except:
        pass
    return "N/A"

@app.route('/')
def index():
    latest = []
    for name in LATEST_NAMES:
        path = os.path.join(DATA_DIR, name)
        stamp = None
        if os.path.islink(path):
            stamp = parse_timestamp(os.readlink(path))
        elif os.path.exists(path):  # published and built copies: the newest timestamped file of the same kind
            kind = name.replace("latest", "")
            newest = sorted(f for f in os.listdir(DATA_DIR)
                            if f.startswith(kind) and f.endswith(".grb") and f != name)
            stamp = parse_timestamp(newest[-1]) if newest else None
        latest.append((name, os.path.exists(path), stamp))

    # List all GRIB files
    files = []
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.startswith(PREFIXES) and filename.endswith('.grb') and filename not in LATEST_NAMES:
                filepath = os.path.join(DATA_DIR, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    files.append({
                        'name': filename,
                        'timestamp': parse_timestamp(filename),
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'size': format_size(stat.st_size),
                        'mtime': stat.st_mtime
                    })
    
    # Sort by modification time, newest first
    files.sort(key=lambda x: x['mtime'], reverse=True)
    
    return render_template_string(
        INDEX_TEMPLATE,
        latest=latest,
        files=files
    )

def _latest_route(name):
    def view():
        if not os.path.exists(os.path.join(DATA_DIR, name)):
            abort(404, description="Latest file not ready yet")
        return send_from_directory(DATA_DIR, name, as_attachment=True)
    view.__name__ = "latest_" + name.split("_")[0]
    return view


for _name in LATEST_NAMES:
    app.add_url_rule(f"/{_name}", view_func=_latest_route(_name))

@app.route('/files/<filename>')
def download_file(filename):
    # Security: only allow files matching the expected pattern
    if not (filename.startswith(PREFIXES) and filename.endswith('.grb')):
        abort(404, description="File not found")
    
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        abort(404, description="File not found")
    
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
