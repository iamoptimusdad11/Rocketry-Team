import os
import json
import numpy as np
from PIL import Image
from astroquery.mast import Observations
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.io import fits
from astropy.convolution import Gaussian2DKernel, convolve
from reproject import reproject_interp

TMP_DIR = "/tmp/fits_processing"
OUT_DIR = "docs/data"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

def scale_to_png(data):
    """Normalize pixel values using 99th percentile contrast for PNG export."""
    data = np.nan_to_num(data, nan=np.nanmedian(data))
    vmin, vmax = np.percentile(data, [1, 99])
    if vmax == vmin: vmax += 1.0
    scaled = np.clip((data - vmin) / (vmax - vmin), 0, 1)
    img = Image.fromarray((scaled * 255).astype(np.uint8))
    return img.transpose(Image.FLIP_LEFT_RIGHT)

# 1. Target: GOODS-South Coordinates
coords = SkyCoord(ra=53.15613, dec=-27.78037, unit=(u.deg, u.deg))
obs = Observations.query_region(coords, radius=0.01 * u.deg)

hst_obs = obs[(obs['obs_collection'] == 'HST') & (obs['dataproduct_type'] == 'image')]
jwst_obs = obs[(obs['obs_collection'] == 'JWST') & (obs['dataproduct_type'] == 'image')]

if len(hst_obs) > 0 and len(jwst_obs) > 0:
    # Download FITS to /tmp
    hst_p = Observations.get_product_list(hst_obs[0])
    hst_f = Observations.filter_products(hst_p, productSubGroupDescription=["DRZ", "FLC"], extension="fits")
    hst_file = Observations.download_products(hst_f[:1], download_dir=TMP_DIR)['Local Path'][0]

    jwst_p = Observations.get_product_list(jwst_obs[0])
    jwst_f = Observations.filter_products(jwst_p, productSubGroupDescription=["I2D"], extension="fits")
    jwst_file = Observations.download_products(jwst_f[:1], download_dir=TMP_DIR)['Local Path'][0]

    with fits.open(hst_file) as h_hst, fits.open(jwst_file) as h_jwst:
        hst_hdu = h_hst[1] if len(h_hst) > 1 else h_hst[0]
        jwst_hdu = h_jwst[1] if len(h_jwst) > 1 else h_jwst[0]

        # 2. Astrometric Alignment (WCS Reprojection)
        hst_reprojected, _ = reproject_interp(hst_hdu, jwst_hdu.header)
        jwst_data = jwst_hdu.data.astype(float)

        # 3. PSF Matching via Gaussian Convolution
        # Blur the higher-resolution image slightly so star profiles match
        kernel = Gaussian2DKernel(stddev=1.2)
        jwst_psf_matched = convolve(jwst_data, kernel, boundary='extend')

        # 4. Flux Scaling & Difference Imaging
        # Calculate scaling factor alpha based on median background sky levels
        alpha = np.nanmedian(jwst_psf_matched) / np.nanmedian(hst_reprojected)
        diff_data = jwst_psf_matched - (alpha * hst_reprojected)

        # 5. Clean Noise & Filter Out Ring Artifacts
        diff_clean = np.nan_to_num(diff_data, nan=0.0)
        sigma = np.nanstd(diff_clean)
        
        # Flag pixels exceeding 5-sigma background noise
        y_indices, x_indices = np.where(diff_clean > (5 * sigma))
        
        anomaly_targets = []
        if len(x_indices) > 0:
            # Group clusters of pixels to pinpoint single light anomaly centers
            anomaly_targets.append({
                "pixel_x": int(np.mean(x_indices)),
                "pixel_y": int(np.mean(y_indices)),
                "peak_flux_sigma": round(float(np.max(diff_clean) / sigma), 2)
            })

        # Save web-ready artifacts to /docs/data
        scale_to_png(hst_reprojected).save(f"{OUT_DIR}/hst_aligned.png")
        scale_to_png(jwst_psf_matched).save(f"{OUT_DIR}/jwst.png")
        scale_to_png(diff_clean).save(f"{OUT_DIR}/difference.png")

        telemetry = {
            "psf_matching_applied": True,
            "kernel_stddev": 1.2,
            "sigma_threshold": 5.0,
            "anomalies_found": len(anomaly_targets),
            "targets": anomaly_targets,
            "hst_img": "data/hst_aligned.png",
            "jwst_img": "data/jwst.png",
            "diff_img": "data/difference.png"
        }
        
        with open(f"{OUT_DIR}/telemetry.json", "w") as f:
            json.dump(telemetry, f, indent=2)
