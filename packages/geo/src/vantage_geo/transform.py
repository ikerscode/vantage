from affine import Affine
from rasterio.transform import rowcol, xy
from rasterio.windows import Window, bounds as window_bounds, from_bounds


def xy_to_rowcol(transform: Affine, x: float, y: float) -> tuple[int, int]:
    """Geo coordinate -> (row, col) pixel indices for the given affine transform."""
    row, col = rowcol(transform, x, y)
    return int(row), int(col)


def rowcol_to_xy(
    transform: Affine, row: int, col: int, offset: str = "center"
) -> tuple[float, float]:
    """(row, col) pixel indices -> geo coordinate (of the pixel center by default)."""
    x, y = xy(transform, row, col, offset=offset)
    return float(x), float(y)


def bounds_to_window(
    transform: Affine, bounds: tuple[float, float, float, float]
) -> Window:
    """Geo bounds (left, bottom, right, top) -> a rasterio Window for windowed reads."""
    left, bottom, right, top = bounds
    return from_bounds(left, bottom, right, top, transform=transform)


def window_to_bounds(
    transform: Affine, window: Window
) -> tuple[float, float, float, float]:
    """A rasterio Window -> geo bounds (left, bottom, right, top)."""
    return window_bounds(window, transform=transform)
