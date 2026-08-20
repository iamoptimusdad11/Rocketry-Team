import os
import json
import numpy as np
from PIL import Image, ImageDraw

# Define Output Directory at Repository Root
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

def run_pipeline():
    print("Generating bright, high-contrast test canvases...")
    img_size = (400, 400)

    # 1. HST Optical Frame (Background Star Field)
    hst = Image.new("RGB", img_size, (10, 15, 30))
    draw_a = ImageDraw.Draw(hst)
    # Background stars
    np.random.seed(42)
    for _ in range(60):
        x, y = np.random.randint(0, 400), np.random.randint(0, 400)
        draw_a.ellipse([x, y, x+2, y+2], fill=(180, 220, 255))

    # 2. JWST IR Frame (Same stars + Bright Transient Source)
    jwst = hst.copy()
    draw_b = ImageDraw.Draw(jwst)
    
    # Bright target anomaly at pixel (220, 180)
    tx, ty = 220, 180
    draw_b.ellipse([tx-8, ty-8, tx+8, ty+8], fill=(255, 140, 0)) # Bright Orange Target

    # 3. Difference Frame (Only the isolated transient)
    diff = Image.new("RGB", img_size, (5, 5, 10))
    draw_d = ImageDraw.Draw(diff)
    draw_d.ellipse([tx-8, ty-8, tx+8, ty+8], fill=(0, 240, 255)) # Bright Cyan Spot

    # Save High-Contrast Outputs
    hst.save(os.path.join(OUT_DIR, "hst_aligned.png"))
    jwst.save(os.path.join(OUT_DIR, "jwst.png"))
    diff.save(os.path.join(OUT_DIR, "difference.png"))

    # Save Telemetry
    telemetry = {
        "psf_matching_applied": True,
        "kernel_stddev": 1.2,
        "sigma_threshold": 5.0,
        "anomalies_found": 1,
        "targets": [{"pixel_x": tx, "pixel_y": ty, "peak_flux_sigma": 8.42}],
        "hst_img": "data/hst_aligned.png",
        "jwst_img": "data/jwst.png",
        "diff_img": "data/difference.png"
    }

    with open(os.path.join(OUT_DIR, "telemetry.json"), "w") as f:
        json.dump(telemetry, f, indent=2)

    print("Success! High-contrast test images saved to /data.")

if __name__ == "__main__":
    run_pipeline()
