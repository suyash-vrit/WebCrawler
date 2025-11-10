# webview_gui/app.py
import webview
from flask import Flask, render_template, request, jsonify
import threading, subprocess, json, uuid, sys, platform, os
from pathlib import Path
import time

# app Flask & paths
app = Flask(__name__, template_folder="templates")
app.config["TEMPLATES_AUTO_RELOAD"] = True

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
CRAWLER_ROOT   = PROJECT_ROOT / "crawler"
CRAWLER_SCRIPT = CRAWLER_ROOT / "crawl_seeded.py"
SCRAPED_ROOT   = CRAWLER_ROOT / "scraped"
SEEDS_FILE     = CRAWLER_ROOT / "seeds.txt"

CRAWL = {"running": False, "logs": [], "results": [], "proc": None}

def log(msg: str, level: str = "info"):
    colors = {"info": "blue", "error": "red", "success": "green", "debug": "gray"}
    CRAWL["logs"].append({
        "id": str(uuid.uuid4()),
        "msg": str(msg),
        "level": colors.get(level, "blue"),
        "time": __import__("time").strftime("%H:%M:%S")
    })

# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    if CRAWL["running"]:
        return jsonify({"error": "A crawl is already running"}), 400

    data = request.json
    cmd = [sys.executable, str(CRAWLER_SCRIPT)]

    if data.get("url"):
        cmd += ["--url", data["url"].strip()]
    elif data.get("seedfile"):
        seed_path = data["seedfile"].strip() or str(SEEDS_FILE)
        cmd += ["--seedfile", seed_path]
    else:
        return jsonify({"error": "Provide URL or seed file"}), 400

    if data.get("prioritize"): 
        cmd += ["--prioritize", data["prioritize"].strip()]
    if data.get("depth") is not None: 
        cmd += ["--depth", str(int(data["depth"]))]
    if data.get("maxpages") is not None: 
        cmd += ["--maxpages", str(int(data["maxpages"]))]
    if data.get("blocked"):
        blocked = [b.strip() for b in data["blocked"].split() if b.strip()]
        if blocked: cmd += ["--blocked"] + blocked
    if data.get("urlpattern"):
        pat = data["urlpattern"].strip()
        if pat: 
            cmd += ["--urlpattern", pat]

    CRAWL["running"] = True
    CRAWL["logs"] = []
    log("=== NEW CRAWL STARTED ===", "success")
    log(f"Target: {data.get('url') or data.get('seedfile') or 'unknown'}", "info")
    CRAWL["results"] = []
    log("Crawler started …", "success")

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=CRAWLER_ROOT
            )
            CRAWL["proc"] = proc
            for line in proc.stdout:
                line = line.rstrip()
                if not line: continue
                if "[ERROR]" in line: log(line, "error")
                elif "Done" in line or "wrote" in line: log(line, "success")
                else: log(line, "info")
            proc.wait()
            if proc.returncode == 0:
                log("Crawl finished", "success")
                _load_results()
            else:
                log(f"Exited with code {proc.returncode}", "error")
        except Exception as e:
            log(f"Exception: {e}", "error")
        finally:
            CRAWL["running"] = False
            CRAWL["proc"] = None

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop():
    if CRAWL["proc"]:
        CRAWL["proc"].terminate()
        log("Crawler stopped by user", "error")
        CRAWL["running"] = False
    return jsonify({"status": "stopped"})

@app.route("/status")
def status():
    return jsonify({
        "running": CRAWL["running"],
        "logs": CRAWL["logs"][-200:],
        "results": CRAWL["results"]
    })


def _load_results():
    results = []
    for dir_path in SCRAPED_ROOT.iterdir():
        if not dir_path.is_dir():
            continue
        jsonl = dir_path / "index.jsonl"
        if not jsonl.exists():
            continue

        seed_url = None
        with jsonl.open(encoding="utf-8") as f:
            first = f.readline()
            if first:
                try:
                    seed_url = json.loads(first).get("url")
                except:
                    pass

        if not seed_url:
            seed_url = f"http://{dir_path.name.replace('_single', '')}"

        # STORE **ABSOLUTE PATH** as string
        abs_path = str(dir_path.resolve())

        results.append({
            "seed": seed_url,
            "directory": str(dir_path.relative_to(PROJECT_ROOT)),  # for display
            "abs_path": abs_path  # for opening
        })

    CRAWL["results"] = results

# ----------------------------------------------------------------------
# PYWEBVIEW API CLASS
# ----------------------------------------------------------------------
class Api:
    def open_folder(self, path: str):
        """Open folder in native file explorer."""
        folder = Path(path).resolve()
        print(folder)
        if not folder.is_dir():
            log(f"Folder not found: {folder}", "error")
            return
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(folder)
            elif system == "Darwin":
                subprocess.run(["open", str(folder)], check=True)
            else:
                subprocess.run(["xdg-open", str(folder)], check=True)
        except Exception as e:
            log(f"Failed to open folder: {e}", "error")

# ----------------------------------------------------------------------
def _flask():
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)

# ----------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=_flask, daemon=True).start()

    time.sleep(1) # Give flask time to start
    # Create window and attach API
    window = webview.create_window(
        title="WebCrawler GUI",
        url="http://127.0.0.1:5000",
        width=1280,
        height=820,
        resizable=True,
        text_select=True,
        js_api=Api()   # This enables window.pywebview.api
    )
    webview.start()