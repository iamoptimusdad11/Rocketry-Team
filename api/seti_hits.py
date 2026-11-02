from http.server import BaseHTTPRequestHandler
import json
import os


ROOT = os.path.dirname(os.path.dirname(__file__))
STATIC_RESULT = os.path.join(ROOT, "data", "seti_hits.json")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with open(STATIC_RESULT, "r", encoding="utf-8") as source:
                result = json.load(source)
            status_code = 200
        except Exception as exc:
            result = {
                "status": "error",
                "message": "Static SETI analysis result is unavailable",
                "backend": "Unavailable",
                "accelerated": False,
                "spectrum_row": [],
                "candidates": [],
            }
            status_code = 503

        body = json.dumps(result).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
