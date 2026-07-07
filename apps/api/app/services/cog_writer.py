import numpy as np
from affine import Affine
from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles


def write_cog_bytes(rgba: np.ndarray, transform: Affine, crs: str) -> bytes:
    """RGBA uint8 array (H, W, 4) + affine transform + CRS -> valid Cloud-Optimized GeoTIFF bytes."""
    height, width, bands = rgba.shape
    src_profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": bands,
        "dtype": rgba.dtype,
        "crs": crs,
        "transform": transform,
    }
    dst_profile = cog_profiles.get("deflate")

    with MemoryFile() as src_mem:
        with src_mem.open(**src_profile) as src_dataset:
            for band_index in range(bands):
                src_dataset.write(rgba[:, :, band_index], band_index + 1)

            with MemoryFile() as dst_mem:
                cog_translate(src_dataset, dst_mem.name, dst_profile, in_memory=True, quiet=True)
                return dst_mem.read()
