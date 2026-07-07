from affine import Affine

from vantage_geo.transform import (
    bounds_to_window,
    rowcol_to_xy,
    window_to_bounds,
    xy_to_rowcol,
)

# Typical 10m-resolution UTM grid, origin at (500000, 4649000), north-up.
TRANSFORM = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 4649000.0)


def test_rowcol_to_xy_hand_computed():
    x, y = rowcol_to_xy(TRANSFORM, 0, 0)

    assert x == 500005.0
    assert y == 4648995.0


def test_xy_to_rowcol_hand_computed():
    row, col = xy_to_rowcol(TRANSFORM, 500005.0, 4648995.0)

    assert (row, col) == (0, 0)


def test_rowcol_xy_round_trip():
    for row, col in [(0, 0), (10, 20), (137, 42)]:
        x, y = rowcol_to_xy(TRANSFORM, row, col)
        round_tripped = xy_to_rowcol(TRANSFORM, x, y)
        assert round_tripped == (row, col)


def test_bounds_window_round_trip():
    bounds = (500100.0, 4648000.0, 500300.0, 4648800.0)

    window = bounds_to_window(TRANSFORM, bounds)
    round_tripped = window_to_bounds(TRANSFORM, window)

    assert round_tripped == bounds
