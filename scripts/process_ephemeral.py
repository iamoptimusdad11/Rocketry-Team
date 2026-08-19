import os
import json
import numpy as np
from PIL import Image
from astroquery.mast import Observations
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.io import fits
from reproject import reproject_interp

# 1. Temporary directory on runner (wiped when job finishes)
TMP_DIR = "/tmp/fits_processing"
OUT_DIR = "docs/data"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

def scale_to_png(data):
    """Normalize pixel values to 8-bit PNG canvas format."""
    data = np.nan_to_num(data, nan=np.nanmedian(data))
    vmin, vmax = np.percentile(data, [1, 99])
    if vmax == vmin: vmax += 1.0
    scaled = np.clip((data - vmin) / (vmax - vmin), 0, 1)
    img = Image.fromarray((scaled * 255).astype(np.uint8))
    return img.transpose(Image.FLIP_LEFT_RIGHT)

# 2. Target: GOODS-South Coordinates
coords = SkyCoord(ra=53.15613, dec=-27.78037, unit=(u.deg, u.deg))
obs = Observations.query_region(coords, radius=0.01 * u.deg)

hst_obs = obs[(obs['obs_collection'] == 'HST') & (obs['dataproduct_type'] == 'image')]
jwst_obs = obs[(obs['obs_collection'] == 'JWST') & (obs['dataproduct_type'] == 'image')]

if len(hst_obs) > 0 and len(jwst_obs) > 0:
    # Download FITS to /tmp (Ephemeral Storage)
    hst_p = Observations.get_product_list(hst_obs[0])
    hst_f = Observations.filter_products(hst_p, productSubGroupDescription=["DRZ", "FLC"], extension="fits")
    hst_file = Observations.download_products(hst_f[:1], download_dir=TMP_DIR)['Local Path'][0]

    jwst_p = Observations.get_product_list(jwst_obs[0])
    jwst_f = Observations.filter_products(jwst_p, productSubGroupDescription=["I2D"], extension="fits")
    jwst_file = Observations.download_products(jwst_f[:1], download_dir=TMP_DIR)['Local Path'][0]

    # Open FITS and extract headers/data
    with fits.open(hst_file) as h_hst, fits.open(jwst_file) as h_jwst:
        hst_hdu = h_hst[1] if len(h_hst) > 1 else h_hst[0]
        jwst_hdu = h_jwst[1] if len(h_jwst) > 1 else h_jwst[0]

        # 3. WCS Reprojection: Re-grid HST to match JWST's exact orientation/pixel grid
        hst_reprojected, _ = reproject_interp(hst_hdu, jwst_hdu.header)

        # 4. Math: Scale baseline flux and calculate Difference Image
        jwst_data = jwst_hdu.data.astype(float)
        alpha = np.nanmedian(jwst_data) / np.nanmedian(hst_reprojected)
        diff_data = jwst_data - (alpha * hst_reprojected)

        # 5. Anomaly Detection: Flag pixels exceeding 5-sigma background noise
        sigma = np.nanstd(diff_data)
        anomalies = np.where(diff_data > (5 * sigma))
        anomaly_detected = len(anomalies[0]) > 0

        # Save ONLY lightweight outputs to /docs/data (Raw FITS in /tmp are lost)
        scale_to_png(hst_reprojected).save(f"{OUT_DIR}/hst_aligned.png")
        scale_to_png(jwst_data).save(f"{OUT_DIR}/jwst.png")
        scale_to_png(diff_data).save(f"{OUT_DIR}/difference.png")

        telemetry = {
            "anomaly_detected": bool(anomaly_detected),
            "sigma_threshold": 5.0,
            "anomaly_count": int(len(anomalies[0])),
            "hst_img": "data/hst_aligned.png",
            "jwst_img": "data/jwst.png",
            "diff_img": "data/difference.png"
        }
        with open(f"{OUT_DIR}/telemetry.json", "w") as f:
            json.dump(telemetry, f, indent=2)
