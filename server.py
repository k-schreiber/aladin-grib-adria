from flask import Flask, send_from_directory, abort
import os

app = Flask(__name__)
DATA_DIR = os.environ.get("OUTDIR", "/data")
LATEST_NAME = "aladin_adriacenter_latest.grb2"

@app.route('/')
def index():
    return f"Available file: /{LATEST_NAME}\n"

@app.route(f'/{LATEST_NAME}')
def latest():
    path = os.path.join(DATA_DIR, LATEST_NAME)
    if not os.path.exists(path):
        abort(404, description="File not ready yet")
    return send_from_directory(DATA_DIR, LATEST_NAME, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
