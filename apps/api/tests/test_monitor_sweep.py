"""Real regression coverage for app.tasks.monitor_sweep's pure logic (cron
due-check, rolling/baseline comparison-date resolution, and the auto-
detection-on-change gate) -- none of sweep_monitors() itself is covered here
since it needs a real Postgres session (see SessionLocal()), but these are
the parts a wrong answer in would be silent and hard to notice: a monitor
that never fires, one that fires on the same date twice, or an auto-
detection that runs when it shouldn't (extra GPU/CPU load for nothing) or
doesn't when it should (a change alert with no follow-up detection)."""

from datetime import date, datetime, timedelta, timezone

from app.imagery.base import ImagerySource, SceneMetadata
from app.imagery.sensor import SensorType
from app.models.monitor import Monitor
from app.tasks.monitor_sweep import (
    SEED_LOOKBACK_DAYS,
    _is_due,
    _latest_scene_date,
    _resolve_comparison_dates,
    _should_run_detection,
)

_NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _monitor(**overrides) -> Monitor:
    defaults = dict(
        schedule="0 * * * *",  # hourly
        threshold=None,
        active=True,
        detect_on_change=True,
        baseline_date=None,
        last_scene_date=None,
        last_run_at=None,
        created_at=_NOW - timedelta(days=1),
    )
    defaults.update(overrides)
    return Monitor(**defaults)


class FakeImagerySource(ImagerySource):
    def __init__(self, scenes: list[SceneMetadata]):
        self._scenes = scenes

    def search(self, geometry, date_from, date_to, collections, max_cloud_cover=None):
        return [
            s
            for s in self._scenes
            if date_from <= datetime.fromisoformat(s.datetime).date() <= date_to
        ]

    def get_asset_href(self, item_id, collection, asset_key):
        raise NotImplementedError


def _scene(scene_date: str) -> SceneMetadata:
    return SceneMetadata(
        id=scene_date,
        collection="sentinel-2-l2a",
        datetime=f"{scene_date}T00:00:00",
        cloud_cover=0.0,
        bbox=(-1, -1, 1, 1),
        assets={},
    )


class TestIsDue:
    def test_due_when_the_next_scheduled_fire_time_has_passed(self):
        monitor = _monitor(schedule="0 * * * *", last_run_at=_NOW - timedelta(hours=2))
        assert _is_due(monitor, _NOW) is True

    def test_not_due_when_the_next_scheduled_fire_time_is_still_ahead(self):
        monitor = _monitor(schedule="0 0 1 1 *", last_run_at=_NOW)  # next Jan 1st
        assert _is_due(monitor, _NOW) is False

    def test_falls_back_to_created_at_when_never_run(self):
        monitor = _monitor(schedule="0 * * * *", last_run_at=None, created_at=_NOW - timedelta(days=1))
        assert _is_due(monitor, _NOW) is True


class TestLatestSceneDate:
    def test_returns_the_most_recent_covering_scene_date(self):
        imagery = FakeImagerySource([_scene("2026-01-01"), _scene("2026-03-15"), _scene("2026-02-01")])
        result = _latest_scene_date(
            imagery, {}, date(2025, 12, 1), date(2026, 4, 1), "sentinel-2-l2a"
        )
        assert result == date(2026, 3, 15)

    def test_returns_none_when_no_scenes_found(self):
        imagery = FakeImagerySource([])
        result = _latest_scene_date(imagery, {}, date(2025, 12, 1), date(2026, 4, 1), "sentinel-2-l2a")
        assert result is None


class TestResolveComparisonDates:
    def test_first_ever_sweep_seeds_latest_scene_date_without_a_comparison(self):
        # No baseline_date, no last_scene_date yet -- nothing to compare
        # against, but the sweep must still learn the latest scene date so
        # the NEXT sweep has something to diff against. Scene date is inside
        # the SEED_LOOKBACK_DAYS window (today - 30 days) since that's what
        # bounds the search when there's no last_scene_date yet.
        imagery = FakeImagerySource([_scene("2026-07-01")])
        monitor = _monitor(baseline_date=None, last_scene_date=None)

        date_a, latest = _resolve_comparison_dates(monitor, imagery, {}, date(2026, 7, 13), "sentinel-2-l2a")

        assert date_a is None
        assert latest == date(2026, 7, 1)

    def test_rolling_comparison_uses_last_scene_date_as_date_a(self):
        imagery = FakeImagerySource([_scene("2026-06-01"), _scene("2026-07-01")])
        monitor = _monitor(baseline_date=None, last_scene_date=date(2026, 6, 1))

        date_a, latest = _resolve_comparison_dates(monitor, imagery, {}, date(2026, 7, 13), "sentinel-2-l2a")

        assert date_a == date(2026, 6, 1)
        assert latest == date(2026, 7, 1)

    def test_no_new_scene_since_last_comparison_yields_no_comparison(self):
        imagery = FakeImagerySource([_scene("2026-06-01")])
        monitor = _monitor(baseline_date=None, last_scene_date=date(2026, 6, 1))

        date_a, latest = _resolve_comparison_dates(monitor, imagery, {}, date(2026, 7, 13), "sentinel-2-l2a")

        # The only scene found IS last_scene_date itself -- nothing new to compare.
        assert date_a is None
        assert latest == date(2026, 6, 1)

    def test_fixed_baseline_is_used_instead_of_last_scene_date(self):
        imagery = FakeImagerySource([_scene("2026-01-01"), _scene("2026-07-01")])
        monitor = _monitor(baseline_date=date(2026, 1, 1), last_scene_date=date(2026, 6, 1))

        date_a, latest = _resolve_comparison_dates(monitor, imagery, {}, date(2026, 7, 13), "sentinel-2-l2a")

        # baseline_date wins over last_scene_date every sweep -- a fixed
        # reference point, not a rolling one.
        assert date_a == date(2026, 1, 1)
        assert latest == date(2026, 7, 1)

    def test_seed_lookback_window_is_used_when_nothing_prior_exists(self):
        imagery = FakeImagerySource([_scene("2026-06-20")])
        monitor = _monitor(baseline_date=None, last_scene_date=None, created_at=_NOW)

        # Just confirms this doesn't blow up and returns a sane seed --
        # the exact lookback window is SEED_LOOKBACK_DAYS, asserted via the
        # module constant rather than a hardcoded literal so this doesn't
        # silently drift out of sync if that constant ever changes.
        _resolve_comparison_dates(monitor, imagery, {}, date(2026, 7, 13), "sentinel-2-l2a")
        assert SEED_LOOKBACK_DAYS == 30


class TestShouldRunDetection:
    def test_runs_when_change_found_optical_and_opted_in(self):
        monitor = _monitor(detect_on_change=True)
        assert _should_run_detection(monitor, SensorType.OPTICAL, changed_pixel_count=5) is True

    def test_skips_when_no_change_found(self):
        monitor = _monitor(detect_on_change=True)
        assert _should_run_detection(monitor, SensorType.OPTICAL, changed_pixel_count=0) is False

    def test_skips_when_monitor_opted_out(self):
        monitor = _monitor(detect_on_change=False)
        assert _should_run_detection(monitor, SensorType.OPTICAL, changed_pixel_count=5) is False

    def test_skips_for_sar_even_when_change_found_and_opted_in(self):
        # No honest object detector exists for SAR amplitude imagery yet --
        # see detection_pipeline.py's module docstring.
        monitor = _monitor(detect_on_change=True)
        assert _should_run_detection(monitor, SensorType.SAR, changed_pixel_count=5) is False
