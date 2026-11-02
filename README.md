# SETI RF Analysis

This site can analyze public Breakthrough Listen HDF5 observations without storing GitHub credentials. The large `.h5` file is downloaded temporarily, analyzed, and deleted. The repository keeps only small JSON and CSV analysis records.

## Use the website

1. Open `seti.html` from the hosted GitHub Pages site.
2. Choose a Berkeley HDF5 file in the catalog.
3. Choose `Auto`, `CPU`, or `CUDA GPU`.
4. Select **Connect / Analyze**.
5. Choose **Download CSV** to export the candidate records currently displayed by the website.

Candidates are statistical hypotheses, not proof of extraterrestrial intelligence. Confirm candidates independently using cadence-off observations and radio-frequency interference checks.

## Run GPU analysis in Google Colab

1. Select **Use Your Own Colab GPU** on the SETI page. The button downloads the notebook and a setup-instructions text file.
2. In Google Colab, select **Upload notebook** and upload `SETI_GPU_Backend.ipynb`.
2. In Colab, select **Runtime > Change runtime type > T4 GPU**.
3. Run every cell from top to bottom.
4. When the final cell prints the public tunnel URL and Bearer token, keep the Colab runtime open.
5. On the website, select an HDF5 file and `CUDA GPU analysis`.
6. Select **Connect / Analyze** and enter:
   - the tunnel URL printed by Colab,
   - the Bearer token printed by Colab.

Do not place the token into this repository, share it publicly, or commit it to a notebook. The notebook generates a new random token each run. The token grants access only to the temporary Colab server and should be treated like a password.

## Safety limits

- Only `https://bldata.berkeley.edu/...` HDF5 URLs are accepted.
- Downloads are capped at 1 GB.
- Analysis is limited to 4096 frequency bins per request.
- Temporary files are removed after analysis and not stored in GitHub.
- GPU mode fails instead of silently falling back to CPU.
- Results use MAD-based narrowband statistics and require verification.
- Cloudflare quick-tunnel URLs and tokens expire when the Colab runtime ends.
- Colab is not a production security boundary. Do not upload private files or store API credentials in notebook cells.
