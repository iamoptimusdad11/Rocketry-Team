import h5py
import fsspec
import numpy as np

# Public Breakthrough Listen S3 dataset (Voyager 1 scan)
S3_VOYAGER_URL = "https://breakthrough.s3.amazonaws.com/voyager/Voyager1.single_coarse.fine_res.h5"

def stream_waterfall_slice(s3_url=S3_VOYAGER_URL, start_bin=1000, num_bins=1024):
    """
    Streams a frequency slice directly from S3 into memory via HTTP range requests.
    """
    print(f"[+] Opening remote HTTPS stream: {s3_url}")
    
    with fsspec.open(s3_url, 'rb') as f:
        with h5py.File(f, 'r') as h5_file:
            data_ds = h5_file['data']
            time_steps = data_ds.shape[0]
            
            # Read only the selected frequency range into RAM
            # Matrix shape: (Time Steps x Frequency Channels)
            matrix = data_ds[0:time_steps, 0, start_bin:start_bin + num_bins]
            
            fch1 = h5_file['data'].attrs.get('fch1', 1420.0) # MHz
            foff = h5_file['data'].attrs.get('foff', -2.835e-6) # MHz/channel
            
            return np.array(matrix), fch1, foff

if __name__ == "__main__":
    data, fch1, foff = stream_waterfall_slice()
    print(f"[✓] Successfully streamed matrix in memory: {data.shape} | Base Freq: {fch1} MHz")
