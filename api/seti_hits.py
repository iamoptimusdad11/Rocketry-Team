from http.server import BaseHTTPRequestHandler
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.analyze_seti import analyze

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            url = query.get("url", ["https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_09539_HIP56445_0027.gpuspec.0002.h5"])[0]
            backend = query.get("backend", ["auto"])[0]
            if backend not in ("auto", "cpu", "gpu"):
                raise ValueError("Invalid backend")
            response_data = analyze(
                url=url,
                start_bin=int(query.get("start_bin", ["0"])[0]),
                num_bins=int(query.get("num_bins", ["256"])[0]),
                snr_threshold=float(query.get("threshold", ["6.5"])[0]),
                backend=backend,
            )

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            # Catch errors and send 200 with the error message for debugging
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "error",
                "message": str(e),
                "spectrum_row": [10, 20, 30, 40, 50, 60, 70, 80]
            }).encode('utf-8'))
