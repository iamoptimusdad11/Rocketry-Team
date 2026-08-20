import os
import json
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from astroquery.skyview import SkyView
from astropy.coordinates import SkyCoord
import astropy.units as u

# 1. Output Path Setup (Root /data directory)
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

def normalize_to_8bit(data):
    """Clean NaN values and stretch array to 0-255 uint8 range for web viewing."""
    data = np.nan_to_num(data, nan=np.nanmedian(data))
    min_v = np.percentile(data, 1)   # Percentile clip to increase contrast
    max_v = np.percentile(data, 99)
    if max_v == min_v:
        max_v = min_v + 1e-5
    clipped = np.clip(data, min_v, max_v)
    normalized = ((clipped - min_v) / (max_v - min_v) * 255).astype(np.uint8)
    return normalized

def run_real_archive_pipeline(target_name="M51", radius_arcmin=10):
    print(f"[*] Querying NASA SkyView Archives for target: {target_name}...")
    coord = SkyCoord.from_name(target_name)

    try:
        # Fetch Real Astronomical FITS Files: Optical (DSS2 Red) & IR (WISE 3.4um)
        images = SkyView.get_images(
            position=coord, 
            survey=['DSS2 Red', 'WISE 3.4'], 
            radius=radius_arcmin * u.arcmin,
            pixels=400
        )

        print("[*] Extracting raw array headers...")
        optical_raw = images[0][0].data
        ir_raw = images[1][0].data

        # Normalize real raw arrays to standard web viewable frames
        optical_norm = normalize_to_8bit(optical_raw)
        ir_norm = normalize_to_8bit(ir_raw)

        # 2. Simple PSF Matching Kernel (Gaussian Smoothing on Optical Frame)
        kernel_sigma = 1.2
        optical_psf_matched = gaussian_filter(optical_norm.astype(float), sigma=kernel_sigma)

        # 3. Calculate Real Array Difference
        diff_array = ir_norm.astype(float) - optical_psf_matched
        diff_clipped = np.clip(diff_array, 0, 255)
        diff_norm = normalize_to_8bit(diff_clipped)

        # 4. Anomaly Detection Engine (Sigma Clipping)
        diff_clean = np.nan_to_num(diff_array)
        median = np.median(diff_clean)
        std_dev = np.std(diff_clean)
        threshold = median + (5.0 * std_dev)

        anomalies = np.argwhere(diff_clean > threshold)
        found_targets = []

        if len(anomalies) > 0:
            # Locate brightest peak in thresholded difference map
            peak_y, peak_x = anomalies[np.argmax(diff_clean[anomalies[:, 0], anomalies[:, 1]])]
            peak_val = diff_clean[peak_y, peak_x]
            sigma_peak = round(float((peak_val - median) / std_dev), 2)

            found_targets.append({
                "pixel_x": int(peak_x),
                "pixel_y": int(peak_y),
                "peak_flux_sigma": sigma_peak
            })

        # 5. Export Images as PNGs directly into root /data
        Image.fromarray(optical_norm).save(os.path.join(OUT_DIR, "hst_aligned.png"))
        Image.fromarray(ir_norm).save(os.path.join(OUT_DIR, "jwst.png"))
        Image.fromarray(diff_norm).save(os.path.join(OUT_DIR, "difference.png"))

        # 6. Build Dynamic Telemetry JSON
        telemetry = {
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

        print(f"[✓] Successfully retrieved and processed {target_name}. Output written to /data.")

    except Exception as e:
        print(f"[!] Archival fetch failed: {e}")
        raise e

if __name__ == "__main__":
    run_pipeline = run_real_archive_pipeline("M51")
