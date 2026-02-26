from django.test import SimpleTestCase

from dashboards.dashboards.dashboard.tools import _normalize_max_features


class DashboardToolsTestCase(SimpleTestCase):
    def test__normalize_max_features_caps_integer_values(self):
        assert _normalize_max_features(10, 4) == 4
        assert _normalize_max_features(0, 4) == 1

    def test__normalize_max_features_keeps_fractional_values(self):
        assert _normalize_max_features(0.5, 4) == 0.5
        assert _normalize_max_features("0.25", 4) == 0.25

    def test__normalize_max_features_supports_non_integer_numeric_input(self):
        assert _normalize_max_features(2.8, 4) == 2
        assert _normalize_max_features("3", 4) == 3

    def test__normalize_max_features_rejects_invalid_values(self):
        assert _normalize_max_features(None, 4) is None
        assert _normalize_max_features(True, 4) is None
        assert _normalize_max_features("abc", 4) is None
