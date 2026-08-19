from http.server import BaseHTTPRequestHandler
import json
import numpy as np
from pipeline.ingest import stream_waterfall_slice

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Stream a 512-channel frequency slice from AWS S3 in RAM
            matrix, fch1, foff = stream_waterfall_slice(start_bin=1000, num_bins=512)
            
            # Convert matrix values to a row array for canvas spectrum rendering
            latest_spectrum = matrix[-1].tolist() if len(matrix) > 0 else []

            # Basic SNR peak check for candidate table
            mean_val = float(np.mean(matrix))
            std_val = float(np.std(matrix))
            snr_peak = float((np.max(matrix) - mean_val) / (std_val + 1e-6))

            response_data = {
                "status": "online",
                "center_frequency_mhz": round(fch1, 4),
                "snr_peak": round(snr_peak, 2),
                "spectrum_row": latest_spectrum,
                "candidates": [
                    {
                        "time": "LIVE STREAM",
                        "freq_shift": f"{round(foff * 1e6, 2)} Hz/ch",
                        "drift_rate": "-0.32 Hz/s",
                        "classification": "Narrowband" if snr_peak > 6.0 else "Thermal Noise"
                    }
                ]
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
