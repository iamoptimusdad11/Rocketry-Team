# SETI RF Analysis

This site analyzes public Breakthrough Listen HDF5 observations without storing GitHub credentials. Temporary HDF5 files are downloaded only for analysis and deleted afterward. The repository stores only small JSON and CSV result records.

## Use the website

1. Open the hosted SETI page.
2. Choose a Berkeley HDF5 file under 1 GB.
3. Select Auto, CPU, or CUDA GPU analysis.
4. Select **Download CSV** to export the candidate records shown by the current result.
5. To use browser WebGPU on your device, select **Use Device GPU - 50% workload**.

Candidates are statistical hypotheses, not proof of extraterrestrial intelligence. Confirm candidates independently with cadence-off observations and radio-frequency interference checks.

## Download the Google Colab backend

Select **Download Colab Notebook + Instructions** on the SETI page. This downloads:

- `SETI_GPU_Backend.ipynb`
- `SETI_GPU_Backend_Instructions.txt`

## Connect your own Colab GPU

1. Upload `SETI_GPU_Backend.ipynb` to Google Colab.
2. Select **Runtime > Change runtime type > T4 GPU**.
3. Select **Runtime > Run all** and keep the runtime open.
4. Copy the HTTPS API URL and one-session Bearer token printed by the final cell.
5. Select an HDF5 file and CUDA GPU mode on the SETI page.
6. Select **Connect Your Own Colab GPU**.
7. Enter the API URL and Bearer token in the connection dialog.
8. Select **Connect**.

The connection token grants access only to your temporary Colab runtime. Do not commit it, share it publicly, or paste it into repository files. The token and tunnel expire when the runtime ends.

## Safety limits

- Only public `https://bldata.berkeley.edu` HDF5 URLs are accepted.
- Downloads are capped at 1 GB.
- Analysis is limited to 4096 frequency bins per request.
- Temporary files are deleted after each analysis.
- GPU mode fails instead of silently falling back to CPU.
- Results are statistical candidates and require verification.
- Colab is not a production security boundary.

## Device GPU mode

**Use Device GPU - 50% workload** uses browser WebGPU. It limits WebGPU processing to half of an available spectrum window, uses the browser's lower-power GPU preference, and creates no network uploads or system-wide GPU configuration changes.

WebGPU cannot guarantee an exact 50% hardware wattage or clock speed; browser policies and operating-system drivers control physical power use. This mode is primarily a bounded visualization/computation assist. Full HDF5 analysis should use CUDA in Colab, while the server remains the CPU fallback.
