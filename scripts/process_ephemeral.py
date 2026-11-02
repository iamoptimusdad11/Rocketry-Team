import os
import json
import csv
import time
from datetime import datetime

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

# Curated rotation list of high-interest transient candidate targets
TARGET_LIST = [
    "M51",
    "M31",
    "M82",
    "M104",
    "NGC 1300",
    "NGC 4038",
    "M1"
]


def normalize_to_8bit(data):
    data = np.nan_to_num(data, nan=np.nanmedian(data))

    min_v = np.percentile(data, 1)
    max_v = np.percentile(data, 99)

    if max_v == min_v:
        max_v = min_v + 1e-5

    clipped = np.clip(data, min_v, max_v)

    return ((clipped - min_v) / (max_v - min_v) * 255).astype(np.uint8)


def generate_fallback_images():
    """
    Generates synthetic optical and IR images if archive retrieval fails.
    """

    shape = (400, 400)

    y, x = np.ogrid[:shape[0], :shape[1]]

    center_y = 200
    center_x = 200

    dist = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)

    optical_raw = (
        1000.0 * np.exp(-dist / 50.0)
        + np.random.normal(0, 10, shape)
    )

    ir_raw = optical_raw.copy()

    transient_y = 150
    transient_x = 250

    transient_blob = (
        800.0
        * np.exp(
            -((x - transient_x) ** 2 + (y - transient_y) ** 2)
            / 8.0
        )
    )

    ir_raw += transient_blob
    ir_raw += np.random.normal(0, 10, shape)

    return optical_raw, ir_raw


def run_real_archive_pipeline(target_name, radius_arcmin=10):

    print(f"[*] Starting processing for {target_name}")

    optical_raw = None
    ir_raw = None

    data_source = "unknown"
    optical_survey = "unknown"
    infrared_survey = "unknown"
    archive_error = None

    try:
        from astroquery.skyview import SkyView
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        print("[*] Resolving target coordinates...")

        coord = SkyCoord.from_name(target_name)

               try:
            print("[*] Requesting DSS2 Red imagery...")

            optical_images = SkyView.get_images(
                position=coord,
                survey=["DSS2 Red"],
                radius=radius_arcmin * u.arcmin,
                pixels=400
            )

            print("[✓] DSS2 Red download successful")

            print("[*] Requesting WISE 3.4 imagery...")

            ir_images = SkyView.get_images(
                position=coord,
                survey=["WISE 3.4"],
                radius=radius_arcmin * u.arcmin,
                pixels=400
            )

            print("[✓] WISE 3.4 download successful")

            optical_raw = optical_images[0][0].data
            ir_raw = ir_images[0][0].data

            data_source = "skyview_archive"
            optical_survey = "DSS2 Red"
            infrared_survey = "WISE 3.4"

            archive_error = None

            print("[✓] SkyView archive retrieval successful")

        except Exception as inner_e:

            archive_error = (
                f"DSS2 Red or WISE 3.4 failed: {inner_e}"
            )

            print(
                f"[!] Archive survey failure: {inner_e}"
            )

            print("[*] Attempting DSS fallback retrieval...")

            images = SkyView.get_images(
                position=coord,
                survey=["DSS"],
                radius=radius_arcmin * u.arcmin,
                pixels=400
            )

            optical_raw = images[0][0].data

            ir_raw = optical_raw + np.random.normal(
                0,
                20,
                optical_raw.shape
            )

            data_source = "skyview_single_survey"
            optical_survey = "DSS"
            infrared_survey = "Synthetic IR"

            print("[✓] DSS fallback retrieval successful")
    except Exception as e:

        archive_error = str(e)

        print(
            f"[!] Archive retrieval failed completely: {e}"
        )

        print("[!] Using synthetic fallback data")

        optical_raw, ir_raw = generate_fallback_images()

        data_source = "synthetic_fallback"
        optical_survey = "Synthetic"
        infrared_survey = "Synthetic"

    # --------------------------------------------------
    # Normalize Images
    # --------------------------------------------------

    optical_norm = normalize_to_8bit(optical_raw)
    ir_norm = normalize_to_8bit(ir_raw)

    # --------------------------------------------------
    # PSF Matching
    # --------------------------------------------------

    kernel_sigma = 1.2

    optical_psf_matched = gaussian_filter(
        optical_norm.astype(float),
        sigma=kernel_sigma
    )

    # --------------------------------------------------
    # Difference Image
    # --------------------------------------------------

    diff_array = ir_norm.astype(float) - optical_psf_matched

    diff_clipped = np.clip(diff_array, 0, 255)

    diff_norm = normalize_to_8bit(diff_clipped)

    # --------------------------------------------------
    # Detection Logic
    # --------------------------------------------------

    diff_clean = np.nan_to_num(diff_array)

    median = np.median(diff_clean)

    std_dev = np.std(diff_clean)

    if std_dev == 0:
        std_dev = 1.0

    threshold = median + (5.0 * std_dev)

    anomalies = np.argwhere(diff_clean > threshold)

    found_targets = []

    if len(anomalies) > 0:

        peak_y, peak_x = anomalies[
            np.argmax(
                diff_clean[
                    anomalies[:, 0],
                    anomalies[:, 1]
                ]
            )
        ]

        peak_val = diff_clean[peak_y, peak_x]

        sigma_peak = round(
            float((peak_val - median) / std_dev),
            2
        )

        found_targets.append(
            {
                "pixel_x": int(peak_x),
                "pixel_y": int(peak_y),
                "peak_flux_sigma": sigma_peak
            }
        )

    # --------------------------------------------------
    # Output Images
    # --------------------------------------------------

    hst_path = os.path.join(OUT_DIR, "hst_aligned.png")
    jwst_path = os.path.join(OUT_DIR, "jwst.png")
    diff_path = os.path.join(OUT_DIR, "difference.png")

    Image.fromarray(optical_norm).save(hst_path)
    Image.fromarray(ir_norm).save(jwst_path)
    Image.fromarray(diff_norm).save(diff_path)

    # --------------------------------------------------
    # Telemetry
    # --------------------------------------------------

    current_timestamp_iso = datetime.utcnow().isoformat()

    telemetry = {
        "timestamp": int(time.time()),
        "iso_timestamp": current_timestamp_iso,

        "target_name": target_name,

        "data_source": data_source,
        "optical_survey": optical_survey,
        "infrared_survey": infrared_survey,
        "archive_error": archive_error,

        "psf_matching_applied": True,
        "kernel_stddev": kernel_sigma,
        "sigma_threshold": 5.0,

        "anomalies_found": len(found_targets),

        "targets": (
            found_targets
            if found_targets
            else [
                {
                    "pixel_x": 200,
                    "pixel_y": 200,
                    "peak_flux_sigma": 0
                }
            ]
        ),

        "hst_img": "data/hst_aligned.png",
        "jwst_img": "data/jwst.png",
        "diff_img": "data/difference.png"
    }

    telemetry_path = os.path.join(
        OUT_DIR,
        "telemetry.json"
    )

    with open(telemetry_path, "w") as f:
        json.dump(telemetry, f, indent=2)

    # --------------------------------------------------
    # Archive History
    # --------------------------------------------------

    archive_path = os.path.join(
        OUT_DIR,
        "archive.json"
    )

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

    # --------------------------------------------------
    # CSV Logging
    # --------------------------------------------------

    csv_path = os.path.join(
        OUT_DIR,
        "subtracted_transient_difference.csv"
    )

    file_exists = os.path.exists(csv_path)

    peak_metric = (
        found_targets[0]["peak_flux_sigma"]
        if found_targets
        else 0.0
    )

    with open(csv_path, "a", newline="") as f:

        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(
                [
                    "Timestamp",
                    "Target",
                    "Source",
                    "Peak_Flux_Sigma",
                    "Anomalies_Found"
                ]
            )

        writer.writerow(
            [
                current_timestamp_iso,
                target_name,
                data_source,
                peak_metric,
                len(found_targets)
            ]
        )

    print()
    print("========== RUN SUMMARY ==========")
    print(f"Target     : {target_name}")
    print(f"Source     : {data_source}")
    print(f"Optical    : {optical_survey}")
    print(f"Infrared   : {infrared_survey}")
    print(f"Detections : {len(found_targets)}")
    print("=================================")
    print()


if __name__ == "__main__":

    time_slot_index = (
        int(time.time() // 600)
        % len(TARGET_LIST)
    )

    selected_target = TARGET_LIST[time_slot_index]

    run_real_archive_pipeline(selected_target)
