from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
import pandas as pd

from dashboards.dashboards.dashboard.index import _with_sample_labels
from dashboards.dashboards.dashboard.tools import (
    _normalize_max_features,
    set_rawfile_action,
)
from maxquant.models import Pipeline, RawFile
from project.models import Project
from user.models import User


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

    def test__with_sample_labels_disambiguates_duplicate_raw_files(self):
        df = _with_sample_labels(
            pd.DataFrame(
                [
                    {"RawFile": "duplicate.raw", "RunKey": "rf6"},
                    {"RawFile": "duplicate.raw", "RunKey": "rf7"},
                    {"RawFile": "unique.raw", "RunKey": "rf8"},
                ]
            )
        )

        self.assertEqual(
            df["SampleLabel"].tolist(),
            ["duplicate.raw [rf6]", "duplicate.raw [rf7]", "unique.raw"],
        )


class DashboardRawFileActionTestCase(TestCase):
    def setUp(self):
        self._run_maxquant = patch(
            "maxquant.Result.run_maxquant.delay", return_value=type("R", (), {"id": "mq-task"})()
        )
        self._rawtools_metrics = patch(
            "maxquant.Result.rawtools_metrics.delay",
            return_value=type("R", (), {"id": "metrics-task"})(),
        )
        self._rawtools_qc = patch(
            "maxquant.Result.rawtools_qc.delay", return_value=type("R", (), {"id": "qc-task"})()
        )
        self._run_maxquant.start()
        self._rawtools_metrics.start()
        self._rawtools_qc.start()
        self.addCleanup(self._run_maxquant.stop)
        self.addCleanup(self._rawtools_metrics.stop)
        self.addCleanup(self._rawtools_qc.stop)

        self.user = User.objects.create_user(
            email="dashboard@example.com", password="pass1234"
        )
        self.project = Project.objects.create(
            name="dashboard-project",
            description="Dashboard project",
            created_by=self.user,
        )
        self.pipeline = Pipeline.objects.create(
            name="dashboard-pipe",
            project=self.project,
            created_by=self.user,
            fasta_file=SimpleUploadedFile("test.fasta", b">protein\nSEQUENCE"),
            mqpar_file=SimpleUploadedFile("test.xml", b"<mqpar></mqpar>"),
            rawtools_args="-p -q -x -u -l -m -r TMT11 -chro 12TB",
        )

    def test__set_rawfile_action_uses_display_ref_for_uuid_prefixed_uppercase_upload(self):
        raw_file = RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("DashboardCase.RAW", b"..."),
            created_by=self.user,
        )
        RawFile.objects.filter(pk=raw_file.pk).update(
            orig_file=f"upload/{uuid4().hex}_DashboardCase.RAW"
        )
        raw_file.refresh_from_db()

        response = set_rawfile_action(
            self.project.slug,
            self.pipeline.slug,
            [raw_file.display_ref],
            "flag",
            user=self.user,
        )

        self.assertEqual(response["status"], "success")
        raw_file.refresh_from_db()
        self.assertTrue(raw_file.flagged)
