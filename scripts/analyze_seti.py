import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlparse

import h5py
import numpy as np
import requests


MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
DEFAULT_URL = (
    "https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/"
    "holding/spliced_blc0001020304050607_guppi_57532_09539_"
    "HIP56445_0027.gpuspec.0002.h5"
)


def download_h5(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("bldata.berkeley.edu",):
        raise ValueError("Only public HTTPS files from bldata.berkeley.edu are allowed")

    with requests.get(url, stream=True, timeout=60, allow_redirects=True) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length", "0"))
        if not 0 < content_length <= MAX_DOWNLOAD_BYTES:
            raise ValueError(
                f"HDF5 file is {content_length} bytes; only files up to {MAX_DOWNLOAD_BYTES} bytes are allowed"
            )

        temporary = tempfile.NamedTemporaryFile(suffix=".h5", delete=False)
        downloaded = 0
        try:
            with temporary:
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise ValueError("HDF5 download exceeded the 1 GB limit")
                    temporary.write(chunk)
            return temporary.name, downloaded
        except Exception:
            os.unlink(temporary.name)
            raise


def load_window(path, start_bin, num_bins):
    with h5py.File(path, "r") as h5:
        dataset = h5["data"]
        shape = dataset.shape
        if len(shape) == 2:
            if shape[1] >= num_bins:
                end = min(start_bin + num_bins, shape[1])
                data = np.asarray(dataset[:, start_bin:end])
            else:
                end = min(start_bin + num_bins, shape[0])
                data = np.asarray(dataset[start_bin:end, :])
        elif len(shape) == 3:
            labels = [str(value).lower() for value in dataset.attrs.get("DIMENSION_LABELS", [])]
            if "frequency" in labels and "time" in labels:
                frequency_axis = labels.index("frequency")
                feed_axis = labels.index("feed_id") if "feed_id" in labels else None
                time_axis = labels.index("time")
                frequency_count = shape[frequency_axis]
                end = min(start_bin + num_bins, frequency_count)
                frequency_slice = slice(start_bin, end)
                selectors = [slice(None)] * 3
                selectors[frequency_axis] = frequency_slice
                if feed_axis is not None:
                    selectors[feed_axis] = 0
                selectors[time_axis] = slice(0, min(277, shape[time_axis]))
                data = np.asarray(dataset[tuple(selectors)])
                if data.ndim == 1:
                    data = data[np.newaxis, :]
                if frequency_axis == 0 and time_axis == 2:
                    data = data.T
                else:
                    data = np.moveaxis(data, frequency_axis, -1)
        elif len(shape) == 4:
            end = min(start_bin + num_bins, shape[3])
            data = np.asarray(dataset[0, :, 0, start_bin:end])
        else:
            raise ValueError(f"Unsupported HDF5 data shape: {shape}")

        fch1 = float(dataset.attrs.get("fch1", 1420.405))
        foff = float(dataset.attrs.get("foff", -2.835e-6))
        return data.astype(np.float32), fch1, foff, list(shape)


def gpu_channel_statistics(matrix, threshold, preferred_backend="auto"):
    try:
        import torch
        use_cuda = preferred_backend == "gpu" and torch.cuda.is_available()
        if preferred_backend == "gpu" and not use_cuda:
            raise RuntimeError("GPU requested but CUDA is unavailable; refusing to run with a different backend")
        device = torch.device("cuda" if use_cuda else "cpu")
        values = torch.as_tensor(matrix, device=device, dtype=torch.float32)
        median = torch.median(values, dim=0).values
        mad = torch.median(torch.abs(values - median), dim=0).values
        noise = torch.clamp(mad * 1.4826, min=1e-6)
        snr = (values.max(dim=0).values - median) / noise
        peak_time = values.argmax(dim=0).values
        snr = snr.detach().cpu().numpy()
        peak_time = peak_time.detach().cpu().numpy()
        backend = "CUDA/PyTorch" if use_cuda else "CPU/PyTorch"
        accelerated = use_cuda
    except RuntimeError as exc:
        raise
    except Exception as exc:
        if preferred_backend == "gpu":
            raise RuntimeError(f"GPU analysis failed: {exc}") from exc
        values = matrix.astype(np.float32)
        median = np.median(values, axis=0)
        mad = np.median(np.abs(values - median), axis=0)
        noise = np.maximum(mad * 1.4826, 1e-6)
        snr = (np.max(values, axis=0) - median) / noise
        peak_time = np.argmax(values, axis=0)
        backend = "CPU/NumPy"
        accelerated = False

    peaks = []
    for channel in np.argsort(snr)[::-1][:20]:
        score = float(snr[channel])
        if score >= threshold:
            peaks.append({
                "channel": int(channel),
                "snr": round(score, 3),
                "time_bin": int(peak_time[channel]),
            })
    return peaks, accelerated, backend


def analyze(url=DEFAULT_URL, start_bin=0, num_bins=256, snr_threshold=6.5, backend="auto"):
    if num_bins < 1 or num_bins > 4096:
        raise ValueError("num_bins must be between 1 and 4096")
    path, downloaded_bytes = download_h5(url)
    try:
        try:
            matrix, fch1, foff, source_shape = load_window(path, start_bin, num_bins)
            peaks, accelerated, backend_name = gpu_channel_statistics(matrix, snr_threshold, backend)
        except OSError as exc:
            timestamp = datetime.now(timezone.utc).isoformat()
            return {
                "status": "error",
                "error": f"HDF5 dataset could not be read synchronously: {exc}",
                "source": url,
                "source_shape": None,
                "downloaded_bytes": downloaded_bytes,
                "max_download_bytes": MAX_DOWNLOAD_BYTES,
                "accelerated": False,
                "backend": "Not run",
                "spectrum_row": [],
                "candidates": [],
                "iso_timestamp": timestamp,
            }
    finally:
        os.unlink(path)

    spectrum = np.mean(matrix, axis=0)
    spectrum = (spectrum - np.min(spectrum)) / max(float(np.max(spectrum) - np.min(spectrum)), 1e-6)
    timestamp = datetime.now(timezone.utc).isoformat()
    candidates = []
    for peak in peaks[:50]:
        frequency_mhz = fch1 + (start_bin + peak["channel"]) * foff
        candidates.append({
            "time": timestamp,
            "frequency_mhz": round(frequency_mhz, 6),
            "freq_shift": f"{peak['channel'] * foff * 1e6:+.2f} Hz/ch",
            "drift_rate": "0.00 Hz/s",
            "classification": "Narrowband candidate",
            "snr": peak["snr"],
            "time_bin": peak["time_bin"],
            "status": "Candidate - requires verification",
        })

    return {
        "status": "online",
        "source": url,
        "source_shape": source_shape,
        "downloaded_bytes": downloaded_bytes,
        "max_download_bytes": MAX_DOWNLOAD_BYTES,
        "matrix_shape": list(matrix.shape),
        "start_bin": start_bin,
        "num_bins": num_bins,
        "center_frequency_mhz": fch1,
        "channel_spacing_mhz": foff,
        "snr_peak": peaks[0]["snr"] if peaks else 0.0,
        "snr_threshold": snr_threshold,
        "accelerated": accelerated,
        "backend": backend_name,
        "spectrum_row": np.round(spectrum * 255.0).astype(int).tolist(),
        "candidates": candidates,
        "iso_timestamp": timestamp,
    }


def write_csv(path, candidates):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=[
            "time", "frequency_mhz", "freq_shift", "drift_rate",
            "classification", "snr", "time_bin", "status",
        ])
        writer.writeheader()
        writer.writerows(candidates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--start-bin", type=int, default=0)
    parser.add_argument("--num-bins", type=int, default=256)
    parser.add_argument("--threshold", type=float, default=6.5)
    parser.add_argument("--backend", choices=("auto", "cpu", "gpu"), default="auto")
    parser.add_argument("--output", default="data/seti_hits.json")
    parser.add_argument("--csv-output", default="data/seti_candidates.csv")
    args = parser.parse_args()

    result = analyze(args.url, args.start_bin, args.num_bins, args.threshold, args.backend)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    write_csv(args.csv_output, result["candidates"])
    print(json.dumps({
        "backend": result["backend"],
        "accelerated": result["accelerated"],
        "downloaded_bytes": result["downloaded_bytes"],
        "matrix_shape": result["matrix_shape"],
        "candidates": len(result["candidates"]),
        "json": args.output,
        "csv": args.csv_output,
    }))


if __name__ == "__main__":
    main()
