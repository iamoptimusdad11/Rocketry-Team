import os
import json
import csv
import time
import tempfile
from datetime import datetime, timezone

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.ndimage import zoom

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

SKYVIEW_SURVEY_CATALOG = {
    "optical": [
        ("DSS2 Red", "Ground/DSS"),
        ("GALEX Near UV", "GALEX"),
    ],
    "infrared": [
        ("2MASS-K", "2MASS"),
        ("WISE 3.4", "WISE"),
        ("WISE 12", "WISE"),
        ("WISE 22", "WISE"),
    ],
}


def discover_mast_collections(coord, radius_arcmin):
    """Discover public NASA/MAST observations available for a target."""
    try:
        from astroquery.mast import Observations
        import astropy.units as u

        observations = Observations.query_region(
            coord,
            radius=radius_arcmin * u.arcmin
        )
        public = observations[
            observations["dataRights"] == "PUBLIC"
        ] if "dataRights" in observations.colnames else observations

        if len(public) == 0:
            return []

        collections = sorted(set(str(value) for value in public["obs_collection"]))
        return collections
    except Exception as exc:
        print(f"[!] MAST collection discovery failed: {exc}")
        return []


def read_mast_science_image(file_path):
    """Read the first 2D science extension with a celestial WCS."""
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(file_path, memmap=False) as hdul:
        for hdu in hdul:
            if hdu.data is None or getattr(hdu.data, "ndim", 0) != 2:
                continue
            try:
                wcs = WCS(hdu.header)
                if wcs.has_celestial:
                    return np.asarray(hdu.data, dtype=float), wcs
            except Exception:
                continue
    return None


def query_and_align_mast_images(coord, radius_arcmin, mission_pairs=("HST", "JWST")):
    """Download one public calibrated FITS image from each requested mission pair."""
    try:
        from astroquery.mast import Observations
        import astropy.units as u

        observations = Observations.query_region(
            coord,
            radius=radius_arcmin * u.arcmin
        )
        if len(observations) == 0 or "obs_collection" not in observations.colnames:
            return None, []

        public = observations[
            observations["dataRights"] == "PUBLIC"
        ] if "dataRights" in observations.colnames else observations

        mast_results = {}
        mast_products = []

        for mission in mission_pairs:
            mission_rows = public[public["obs_collection"] == mission]
            if len(mission_rows) == 0:
                continue

            mission_rows = mission_rows[::-1][:8]
            products = Observations.get_product_list(mission_rows)
            if len(products) == 0:
                continue

            filename_column = products["productFilename"] if "productFilename" in products.colnames else products["productFilename"]
            fits_mask = np.array([
                str(name).lower().endswith((".fits", ".fits.gz"))
                for name in filename_column
            ])
            fits_products = products[fits_mask]
            if len(fits_products) == 0:
                continue

            if "productType" in fits_products.colnames:
                science_mask = np.array([
                    str(value).upper() in ("SCIENCE", "SCI")
                    for value in fits_products["productType"]
                ])
                if np.any(science_mask):
                    fits_products = fits_products[science_mask]

            preferred_names = np.array([
                any(marker in str(name).lower() for marker in (
                    "_x2d.fits", "_i2d.fits", "_drc.fits", "_cal.fits"
                ))
                for name in fits_products["productFilename"]
            ])
            if np.any(preferred_names):
                fits_products = fits_products[preferred_names]

            fits_products = fits_products[:1]

            with tempfile.TemporaryDirectory(prefix="mast-") as download_dir:
                try:
                    downloaded = Observations.download_products(
                        fits_products,
                        download_dir=download_dir
                    )
                except Exception as download_error:
                    print(f"[!] MAST {mission} download failed: {download_error}")
                    continue

                for row in downloaded:
                    status = str(row["Status"])
                    file_path = str(row["Local Path"])
                    if status.lower() != "complete" or not os.path.exists(file_path):
                        continue

                    image_result = read_mast_science_image(file_path)
                    if image_result is None:
                        print(f"[!] {mission} file had no 2D celestial science extension")
                        continue

                    image_data, image_wcs = image_result
                    mast_results[mission] = (image_data, image_wcs)
                    mast_products.append(f"{mission}:{os.path.basename(file_path)}")
                    break

        if "HST" not in mast_results or "JWST" not in mast_results:
            return None, mast_products

        hst_data, hst_wcs = mast_results["HST"]
        jwst_data, jwst_wcs = mast_results["JWST"]

        from reproject import reproject_interp
        from astropy.wcs.utils import proj_plane_pixel_scales

        minimum_scale = min(
            proj_plane_pixel_scales(hst_wcs) * 3600.0
        ) if proj_plane_pixel_scales(hst_wcs).size else 0.1
        image_shape = (400, 400)
        angular_span = 10.0 / 60.0

        reference_wcs = hst_wcs.deepcopy()
        aligned_jwst, _ = reproject_interp(
            (jwst_data, jwst_wcs),
            reference_wcs,
            shape_out=image_shape
        )

        hst_resized = resize_to_detector_shape(hst_data, image_shape)
        jwst_resized = resize_to_detector_shape(aligned_jwst, image_shape)
        return (hst_resized, jwst_resized), mast_products
    except Exception as exc:
        print(f"[!] MAST FITS pipeline failed: {exc}")
        return None, []


def normalize_to_8bit(data):
    data = np.nan_to_num(data, nan=np.nanmedian(data))

    min_v = np.percentile(data, 1)
    max_v = np.percentile(data, 99)

    if max_v == min_v:
        max_v = min_v + 1e-5

    clipped = np.clip(data, min_v, max_v)

    return ((clipped - min_v) / (max_v - min_v) * 255).astype(np.uint8)


def resize_to_detector_shape(data, shape=(400, 400)):
    data = np.asarray(data)
    if data.ndim != 2:
        raise ValueError(f"Expected a 2D image, received shape {data.shape}")
    if data.shape == shape:
        return data

    factors = (
        shape[0] / data.shape[0],
        shape[1] / data.shape[1],
    )
    return zoom(data, factors, order=1)


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
    available_sources = []

    data_source = "unknown"
    optical_survey = "unknown"
    infrared_survey = "unknown"
    mast_products = []
    archive_error = None

    try:
        from astroquery.skyview import SkyView
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        print("[*] Resolving target coordinates...")
        coord = SkyCoord.from_name(target_name)
        available_sources = discover_mast_collections(coord, radius_arcmin)
        print(f"[+] MAST collections found: {available_sources or 'none'}")

        try:
            mast_pair, mast_products = query_and_align_mast_images(
                coord,
                radius_arcmin
            )
            if mast_pair is not None:
                optical_raw, ir_raw = mast_pair
                data_source = "mast_fits_aligned"
                optical_survey = "HST science FITS"
                infrared_survey = "JWST science FITS"
                archive_error = None
                print("[+] MAST HST/JWST aligned FITS pair successful")

            else:
                print("[*] MAST HST/JWST pair unavailable; using SkyView surveys")

            if optical_raw is not None and ir_raw is not None:
                raise StopIteration

            optical_raw = None
            for survey, provider in SKYVIEW_SURVEY_CATALOG["optical"]:
                try:
                    print(f"[*] Requesting optical survey: {survey}")
                    images = SkyView.get_images(
                        position=coord,
                        survey=[survey],
                        radius=radius_arcmin * u.arcmin,
                        pixels=400
                    )
                    optical_raw = images[0][0].data
                    optical_survey = survey
                    available_sources.append(f"{provider}:{survey}")
                    print(f"[+] {survey} download successful")
                    break
                except Exception as survey_error:
                    print(f"[!] {survey} unavailable: {survey_error}")

            if optical_raw is None:
                raise RuntimeError("No optical SkyView survey was available")

            ir_raw = None
            for survey, provider in SKYVIEW_SURVEY_CATALOG["infrared"]:
                try:
                    print(f"[*] Requesting infrared survey: {survey}")
                    images = SkyView.get_images(
                        position=coord,
                        survey=[survey],
                        radius=radius_arcmin * u.arcmin,
                        pixels=400
                    )
                    ir_raw = images[0][0].data
                    infrared_survey = survey
                    available_sources.append(f"{provider}:{survey}")
                    print(f"[+] {survey} download successful")
                    break
                except Exception as survey_error:
                    print(f"[!] {survey} unavailable: {survey_error}")

            if ir_raw is None:
                raise RuntimeError("No infrared SkyView survey was available")

            data_source = "skyview_archive"
            archive_error = None

            print("[+] SkyView archive retrieval successful")

        except StopIteration:
            pass
        except Exception as inner_e:
            archive_error = f"DSS2 Red or WISE 3.4 failed: {inner_e}"
            print(f"[!] Archive survey failure: {inner_e}")
            print("[*] Attempting DSS fallback retrieval...")

            images = SkyView.get_images(
                position=coord,
                survey=["DSS"],
                radius=radius_arcmin * u.arcmin,
                pixels=400
            )

            optical_raw = images[0][0].data
            ir_raw = optical_raw + np.random.normal(
                0, 20, optical_raw.shape
            )

            data_source = "skyview_single_survey"
            optical_survey = "DSS"
            infrared_survey = "Synthetic IR"

            print("[+] DSS fallback retrieval successful")

    except Exception as e:
        archive_error = str(e)
        print(f"[!] Archive retrieval failed completely: {e}")
        print("[!] Using synthetic fallback data")

        optical_raw, ir_raw = generate_fallback_images()

        data_source = "synthetic_fallback"
        optical_survey = "Synthetic"
        infrared_survey = "Synthetic"

    # --------------------------------------------------
    # Normalize Images
    # --------------------------------------------------
    optical_raw = resize_to_detector_shape(optical_raw)
    ir_raw = resize_to_detector_shape(ir_raw)
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
    current_timestamp_iso = datetime.now(timezone.utc).isoformat()

    telemetry = {
        "timestamp": int(time.time()),
        "iso_timestamp": current_timestamp_iso,
        "target_name": target_name,
        "data_source": data_source,
        "optical_survey": optical_survey,
        "infrared_survey": infrared_survey,
        "available_sources": sorted(set(available_sources)),
        "mast_products": mast_products,
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

    telemetry_path = os.path.join(OUT_DIR, "telemetry.json")
    with open(telemetry_path, "w") as f:
        json.dump(telemetry, f, indent=2)

    # --------------------------------------------------
    # Archive History
    # --------------------------------------------------
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
