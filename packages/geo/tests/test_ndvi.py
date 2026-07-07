import numpy as np

from vantage_geo.ndvi import compute_ndvi


def test_compute_ndvi_hand_computed():
    nir = np.array([[200.0, 100.0], [50.0, 0.0]], dtype=np.float32)
    red = np.array([[100.0, 100.0], [50.0, 0.0]], dtype=np.float32)

    result = compute_ndvi(nir, red)

    assert result.dtype == np.float32
    np.testing.assert_allclose(result[0, 0], 100.0 / 300.0, rtol=1e-6)
    assert result[0, 1] == 0.0
    assert result[1, 0] == 0.0
    # zero-denominator cell (nir + red == 0) falls back to nodata
    assert np.isnan(result[1, 1])


def test_compute_ndvi_valid_range():
    rng = np.random.default_rng(0)
    nir = rng.uniform(1, 10000, size=(16, 16)).astype(np.float32)
    red = rng.uniform(1, 10000, size=(16, 16)).astype(np.float32)

    result = compute_ndvi(nir, red)

    assert np.all(result >= -1.0) and np.all(result <= 1.0)


def test_compute_ndvi_custom_nodata():
    nir = np.array([[0.0]], dtype=np.float32)
    red = np.array([[0.0]], dtype=np.float32)

    result = compute_ndvi(nir, red, nodata=-999.0)

    assert result[0, 0] == np.float32(-999.0)
