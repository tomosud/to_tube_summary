"""生成済みページ(C:\\temp\\html)をローカルHTTPで配信するだけの小さなサーバー。

YouTube埋め込みは file:// では再生できない(エラー153)ため、http://127.0.0.1:8123 経由で開く。
- 既にサーバーが動いていれば新たに起動しない(多重起動・ポート競合の回避)
- --open <サブパス> : サーバー確認/起動後にブラウザで開く(未起動なら切り離して起動)
"""
import argparse
import html
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8123
HOST = "127.0.0.1"
DEFAULT_ROOT = r"C:\temp\html"
ROOT = os.environ.get("TUBE_PAGES_DIR") or DEFAULT_ROOT
BASE_URL = f"http://{HOST}:{PORT}/"


def is_server_running():
    try:
        with urllib.request.urlopen(BASE_URL, timeout=1.5):
            return True
    except Exception:
        return False


class PagesHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("", "/"):
            self.send_index()
        else:
            super().do_GET()

    def send_index(self):
        root = self.directory
        items = []
        try:
            for name in os.listdir(root):
                full = os.path.join(root, name)
                index = os.path.join(full, "index.html")
                if os.path.isdir(full) and os.path.isfile(index):
                    items.append((os.path.getmtime(index), name, os.path.isfile(os.path.join(full, "Thumbnail.jpg"))))
        except OSError:
            pass
        items.sort(reverse=True)
        rows = []
        for _, name, has_thumb in items:
            q = urllib.parse.quote(name)
            thumb = f'<img src="{q}/Thumbnail.jpg" loading="lazy">' if has_thumb else '<span class="ph"></span>'
            rows.append(f'<a class="item" href="{q}/index.html">{thumb}<span>{html.escape(name.replace("_", " "))}</span></a>')
        body = "\n".join(rows) or "<p>ページがまだありません。</p>"
        page = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><title>要約ページ一覧</title>
<style>
body{{background:#1b1b1b;color:#ddd;font-family:sans-serif;margin:0;padding:20px}}
h1{{font-size:20px;margin:0 0 16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}}
.item{{display:block;background:#262626;border-radius:6px;overflow:hidden;color:#ddd;text-decoration:none}}
.item:hover{{background:#333}}
.item img,.item .ph{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#000}}
.item span:last-child{{display:block;padding:8px 10px;font-size:13px;line-height:1.4}}
</style></head><body>
<h1>要約ページ一覧 ({len(items)})</h1>
<div class="grid">{body}</div>
</body></html>"""
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server():
    os.makedirs(ROOT, exist_ok=True)
    handler = partial(PagesHandler, directory=ROOT)
    try:
        server = ThreadingHTTPServer((HOST, PORT), handler)
    except OSError as e:
        print(f"サーバーを起動できませんでした: {e}")
        return 1
    print(f"配信中: {ROOT} -> {BASE_URL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def spawn_detached():
    exe = sys.executable
    flags = 0
    if os.name == "nt":
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pythonw):
            exe = pythonw
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    subprocess.Popen(
        [exe, os.path.abspath(__file__)],
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", nargs="?", const="", default=None, metavar="SUBPATH",
                        help="サーバー確認/起動後にブラウザで開く(省略時は一覧)")
    args = parser.parse_args()

    running = is_server_running()
    if args.open is None:
        if running:
            print(f"既にサーバーが動いています: {BASE_URL}")
            return 0
        return run_server()

    if not running:
        spawn_detached()
        for _ in range(30):
            time.sleep(0.2)
            if is_server_running():
                break
        else:
            print("サーバーの起動を確認できませんでした")
            return 1
    sub = args.open.lstrip("/")
    webbrowser.open(BASE_URL + sub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
