from flask import Flask, send_from_directory, abort, render_template_string
import os
from datetime import datetime

app = Flask(__name__)
DATA_DIR = os.environ.get("OUTDIR", "/data")
LATEST_NAME = "aladin_adriacenter_latest.grb2"

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
        <strong>Latest Run:</strong> 
        {% if latest_exists %}
            <a href="/{{ latest_name }}">{{ latest_name }}</a>
            {% if latest_timestamp %}
                <span class="timestamp">({{ latest_timestamp }})</span>
            {% endif %}
        {% else %}
            <span style="color: #d32f2f;">Not available yet</span>
        {% endif %}
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
        # Format: aladin_adriacenter_YYYYMMDDHH.grb2
        parts = filename.split('_')
        if len(parts) >= 3:
            ts = parts[2].replace('.grb2', '')
            if len(ts) == 10 and ts.isdigit():
                # Format as YYYY-MM-DD HH:00
                return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:00"
    except:
        pass
    return "N/A"

@app.route('/')
def index():
    # Check if latest file exists
    latest_path = os.path.join(DATA_DIR, LATEST_NAME)
    latest_exists = os.path.exists(latest_path)
    latest_timestamp = None
    
    if latest_exists:
        # Resolve symlink to get actual filename
        if os.path.islink(latest_path):
            actual_file = os.readlink(latest_path)
            latest_timestamp = parse_timestamp(actual_file)
    
    # List all GRIB files
    files = []
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.startswith('aladin_adriacenter_') and filename.endswith('.grb2') and filename != LATEST_NAME:
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
        latest_name=LATEST_NAME,
        latest_exists=latest_exists,
        latest_timestamp=latest_timestamp,
        files=files
    )

@app.route(f'/{LATEST_NAME}')
def latest():
    path = os.path.join(DATA_DIR, LATEST_NAME)
    if not os.path.exists(path):
        abort(404, description="Latest file not ready yet")
    return send_from_directory(DATA_DIR, LATEST_NAME, as_attachment=True)

@app.route('/files/<filename>')
def download_file(filename):
    # Security: only allow files matching the expected pattern
    if not (filename.startswith('aladin_adriacenter_') and filename.endswith('.grb2')):
        abort(404, description="File not found")
    
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        abort(404, description="File not found")
    
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
