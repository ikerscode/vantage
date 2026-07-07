import numpy as np
import rasterio
from affine import Affine
from rasterio.windows import Window, transform as window_transform

from vantage_geo.transform import bounds_to_window


def extract_chip(
    array: np.ndarray,
    transform: Affine,
    bbox: tuple[float, float, float, float],
    *,
    boundless: bool = True,
    fill_value: float = 0,
) -> tuple[np.ndarray, Affine]:
    """Slice a chip out of an in-memory (H, W) or (bands, H, W) array by geo bbox.

    Returns the chip array and the affine transform for that chip's own grid.
    """
    window = bounds_to_window(transform, bbox).round_offsets().round_lengths()
    height, width = array.shape[-2:]
    row_off, col_off = int(window.row_off), int(window.col_off)
    row_stop, col_stop = row_off + int(window.height), col_off + int(window.width)

    if boundless:
        pad_top = max(0, -row_off)
        pad_left = max(0, -col_off)
        pad_bottom = max(0, row_stop - height)
        pad_right = max(0, col_stop - width)
        src_row_off, src_col_off = max(0, row_off), max(0, col_off)
        src_row_stop, src_col_stop = min(height, row_stop), min(width, col_stop)
        chip = array[..., src_row_off:src_row_stop, src_col_off:src_col_stop]
        pad_width = [(0, 0)] * (array.ndim - 2) + [
            (pad_top, pad_bottom),
            (pad_left, pad_right),
        ]
        chip = np.pad(chip, pad_width, mode="constant", constant_values=fill_value)
    else:
        chip = array[..., row_off:row_stop, col_off:col_stop]

    chip_transform = window_transform(window, transform)
    return chip, chip_transform


def extract_chip_from_dataset(
    src: rasterio.DatasetReader,
    bbox: tuple[float, float, float, float],
    band_indexes: list[int] | None = None,
) -> tuple[np.ndarray, Affine]:
    """Windowed, boundless read of a chip directly from an open rasterio dataset."""
    window = bounds_to_window(src.transform, bbox)
    chip = src.read(indexes=band_indexes, window=window, boundless=True, fill_value=0)
    chip_transform = window_transform(window, src.transform)
    return chip, chip_transform
