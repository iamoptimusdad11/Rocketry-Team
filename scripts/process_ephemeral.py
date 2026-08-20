import os
import json
import random
import time
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from astroquery.skyview import SkyView
from astropy.coordinates import SkyCoord
import astropy.units as u

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

# Curated rotation list of high-interest transient candidate targets
TARGET_LIST = ["M51", "M31", "M82", "M104", "NGC 1300", "NGC 4038", "M1"]

def normalize_to_8bit(data):
    data = np.nan_to_num(data, nan=np.nanmedian(data))
    min_v = np.percentile(data, 1)
    max_v = np.percentile(data, 99)
    if max_v == min_v:
        max_v = min_v + 1e-5
    clipped = np.clip(data, min_v, max_v)
    return ((clipped - min_v) / (max_v - min_v) * 255).astype(np.uint8)

def run_real_archive_pipeline(target_name, radius_arcmin=10):
    print(f"[*] Querying NASA SkyView Archives for target: {target_name}...")
    coord = SkyCoord.from_name(target_name)

    try:
        images = SkyView.get_images(
            position=coord, 
            survey=['DSS2 Red', 'WISE 3.4'], 
            radius=radius_arcmin * u.arcmin,
            pixels=400
        )

        optical_raw = images[0][0].data
        ir_raw = images[1][0].data

        optical_norm = normalize_to_8bit(optical_raw)
        ir_norm = normalize_to_8bit(ir_raw)

        kernel_sigma = 1.2
        optical_psf_matched = gaussian_filter(optical_norm.astype(float), sigma=kernel_sigma)

        diff_array = ir_norm.astype(float) - optical_psf_matched
        diff_clipped = np.clip(diff_array, 0, 255)
        diff_norm = normalize_to_8bit(diff_clipped)

        diff_clean = np.nan_to_num(diff_array)
        median = np.median(diff_clean)
        std_dev = np.std(diff_clean)
        threshold = median + (5.0 * std_dev)

        anomalies = np.argwhere(diff_clean > threshold)
        found_targets = []

        if len(anomalies) > 0:
            peak_y, peak_x = anomalies[np.argmax(diff_clean[anomalies[:, 0], anomalies[:, 1]])]
            peak_val = diff_clean[peak_y, peak_x]
            sigma_peak = round(float((peak_val - median) / std_dev), 2)

            found_targets.append({
                "pixel_x": int(peak_x),
                "pixel_y": int(peak_y),
                "peak_flux_sigma": sigma_peak
            })

        Image.fromarray(optical_norm).save(os.path.join(OUT_DIR, "hst_aligned.png"))
        Image.fromarray(ir_norm).save(os.path.join(OUT_DIR, "jwst.png"))
        Image.fromarray(diff_norm).save(os.path.join(OUT_DIR, "difference.png"))

        telemetry = {
            "timestamp": int(time.time()),
            "target_name": target_name,
            "psf_matching_applied": True,
            "kernel_stddev": kernel_sigma,
            "sigma_threshold": 5.0,
            "anomalies_found": len(found_targets),
            "targets": found_targets if found_targets else [{"pixel_x": 200, "pixel_y": 200, "peak_flux_sigma": 0}],
            "hst_img": "data/hst_aligned.png",
            "jwst_img": "data/jwst.png",
            "diff_img": "data/difference.png"
        }

        with open(os.path.join(OUT_DIR, "telemetry.json"), "w") as f:
            json.dump(telemetry, f, indent=2)

        # Log entry into archive.json history file
        archive_path = os.path.join(OUT_DIR, "archive.json")
        history = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, "r") as f:
                    history = json.load(f)
            except Exception:
                history = []

        history.append(telemetry)
        with open(archive_path, "w") as f:
            json.dump(history, f, indent=2)

        print(f"[✓] Processed target {target_name}. Output updated in /data.")

    except Exception as e:
        print(f"[!] Archival fetch failed: {e}")
        raise e

if __name__ == "__main__":
    selected_target = random.choice(TARGET_LIST)
    run_real_archive_pipeline(selected_target)
