from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TestCase
import dash
import pandas as pd

from dashboards.dashboards.dashboard.anomaly import (
    apply_anomaly_flag_changes,
    compute_flag_proposals,
)
from dashboards.dashboards.dashboard.index import (
    _with_sample_labels,
    refresh_qc_table,
    update_kpis,
)
from dashboards.dashboards.dashboard.tools import (
    _normalize_max_features,
    _iter_selected_results,
    dashboard_result_data,
    dashboard_rows,
    dashboard_scope_error,
    detect_anomalies,
    get_protein_groups,
    get_protein_names,
    get_qc_data,
    set_rawfile_action,
)
from maxquant.models import Pipeline, RawFile
from project.models import Project
from user.models import User


class DashboardToolsTestCase(SimpleTestCase):
    def test__dashboard_helpers_extract_rows_and_errors(self):
        payload = {
            "rows": [{"RawFile": "a.raw"}],
            "error": {"kind": "parsing", "message": "Bad parquet"},
        }

        self.assertEqual(dashboard_rows(payload), [{"RawFile": "a.raw"}])
        self.assertEqual(dashboard_scope_error(payload)["kind"], "parsing")
        self.assertEqual(dashboard_result_data({"data": {"A": [1]}}, {}), {"A": [1]})

    @patch("dashboards.dashboards.dashboard.tools.api_get_qc_data")
    def test__get_qc_data_returns_structured_error_for_permission_failures(self, mock_get_qc):
        mock_get_qc.side_effect = PermissionDenied("forbidden")

        result = get_qc_data("proj", "pipe", columns=None, data_range=None, user=object())

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["kind"], "auth")
        self.assertIn("permission", result["error"]["message"].lower())

    @patch("dashboards.dashboards.dashboard.tools.api_get_qc_data", return_value=pd.DataFrame())
    def test__get_qc_data_preserves_true_no_data_state(self, _mock_get_qc):
        result = get_qc_data("proj", "pipe", columns=None, data_range=None, user=object())

        self.assertEqual(result["status"], "no_data")
        self.assertIsNone(result["error"])

    @patch("dashboards.dashboards.dashboard.tools.get_protein_quant_fn")
    def test__get_protein_groups_returns_file_read_error(self, mock_get_fns):
        mock_get_fns.side_effect = FileNotFoundError("missing parquet")

        result = get_protein_groups(
            "proj",
            "pipe",
            protein_names=["P1"],
            columns=["Score"],
            user=object(),
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["kind"], "file_read")

    @patch("dashboards.dashboards.dashboard.tools._protein_group_frame_from_results")
    @patch("dashboards.dashboards.dashboard.tools.get_protein_quant_fn", return_value=[])
    def test__get_protein_names_falls_back_to_protein_groups_text_when_parquet_missing(
        self,
        _mock_get_fns,
        mock_from_results,
    ):
        mock_from_results.return_value = pd.DataFrame(
            [
                {
                    "Majority protein IDs": "P1",
                    "Fasta headers": "Protein 1",
                    "Intensity": 42.0,
                    "RawFile": "demo_01",
                },
                {
                    "Majority protein IDs": "CON__P2",
                    "Fasta headers": "Contaminant",
                    "Intensity": 5.0,
                    "RawFile": "demo_02",
                },
            ]
        )

        result = get_protein_names("proj", "pipe", raw_files=["demo_01"], user=object())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["protein_names"], ["P1"])

    @patch("dashboards.dashboards.dashboard.tools._protein_group_frame_from_results")
    @patch("dashboards.dashboards.dashboard.tools.get_protein_quant_fn", return_value=[])
    def test__get_protein_groups_falls_back_to_protein_groups_text_when_parquet_missing(
        self,
        _mock_get_fns,
        mock_from_results,
    ):
        mock_from_results.return_value = pd.DataFrame(
            [
                {
                    "Majority protein IDs": "P1",
                    "RawFile": "demo_01",
                    "Reporter intensity corrected 1": 100.0,
                    "Reporter intensity corrected 2": 110.0,
                },
                {
                    "Majority protein IDs": "P2",
                    "RawFile": "demo_02",
                    "Reporter intensity corrected 1": 50.0,
                    "Reporter intensity corrected 2": 55.0,
                },
            ]
        )

        result = get_protein_groups(
            "proj",
            "pipe",
            protein_names=["P1"],
            columns=["Reporter intensity corrected"],
            raw_files=["demo_01"],
            user=object(),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["Majority protein IDs"]["0"], "P1")

    @patch("dashboards.dashboards.dashboard.tools._results_for_user")
    @patch("dashboards.dashboards.dashboard.tools._pipelines_for_user")
    def test__iter_selected_results_uses_owner_scoped_queryset_for_non_admins(
        self,
        mock_pipelines_for_user,
        mock_results_for_user,
    ):
        pipeline_obj = object()
        mock_pipelines_for_user.return_value.filter.return_value.first.return_value = pipeline_obj
        owner_queryset = mock_results_for_user.return_value
        owner_queryset.filter.return_value.order_by.return_value = ["owned-result"]

        results = _iter_selected_results("proj", "pipe", user=object())

        self.assertEqual(results, ["owned-result"])
        mock_results_for_user.assert_called_once()
        owner_queryset.filter.assert_called_once_with(raw_file__pipeline=pipeline_obj)

    @patch("dashboards.dashboards.dashboard.tools._results_for_user")
    @patch("dashboards.dashboards.dashboard.tools._pipelines_for_user")
    def test__iter_selected_results_preserves_admin_access_through_results_helper(
        self,
        mock_pipelines_for_user,
        mock_results_for_user,
    ):
        pipeline_obj = object()
        admin_user = object()
        mock_pipelines_for_user.return_value.filter.return_value.first.return_value = pipeline_obj
        admin_queryset = mock_results_for_user.return_value
        admin_queryset.filter.return_value.order_by.return_value = ["admin-result-a", "admin-result-b"]

        results = _iter_selected_results("proj", "pipe", user=admin_user)

        self.assertEqual(results, ["admin-result-a", "admin-result-b"])
        mock_results_for_user.assert_called_once_with(admin_user)

    @patch("dashboards.dashboards.dashboard.tools.ShapAnalysis")
    @patch("dashboards.dashboards.dashboard.tools.predict_model")
    @patch("dashboards.dashboards.dashboard.tools.get_config")
    @patch("dashboards.dashboards.dashboard.tools.create_model")
    @patch("dashboards.dashboards.dashboard.tools.setup")
    def test__detect_anomalies_uses_all_rows_when_use_downstream_is_unknown(
        self,
        mock_setup,
        mock_create_model,
        mock_get_config,
        mock_predict_model,
        mock_shap_analysis,
    ):
        class _Pipeline:
            def transform(self, df):
                return df.copy()

        qc_data = pd.DataFrame(
            {
                "Use Downstream": [None, None, None],
                "MetricA": [1.0, 2.0, 3.0],
                "MetricB": [4.0, 5.0, 6.0],
            },
            index=["rf1", "rf2", "rf3"],
        )
        mock_create_model.return_value = object()
        mock_get_config.return_value = _Pipeline()
        mock_predict_model.return_value = pd.DataFrame(
            {
                "Anomaly": [0, 1, 0],
                "Anomaly_Score": [0.1, 0.9, 0.2],
            },
            index=qc_data.index,
        )
        mock_shap_analysis.return_value.df_shap = pd.DataFrame(
            {
                "MetricB": [0.3, 0.2, 0.1],
                "MetricA": [0.1, 0.4, 0.2],
            },
            index=qc_data.index,
        )

        predictions, shap_values = detect_anomalies(
            qc_data,
            algorithm="iforest",
            columns=["MetricA", "MetricB"],
            fraction=0.05,
        )

        df_train = mock_setup.call_args.args[0]
        self.assertEqual(len(df_train.index), 3)
        self.assertEqual(predictions["Anomaly"].tolist(), [0, 1, 0])
        self.assertEqual(list(shap_values.columns), ["MetricB", "MetricA"])

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

    def test__compute_flag_proposals_returns_preview_without_mutation_side_effects(self):
        qc_data = pd.DataFrame(
            [
                {
                    "RunKey": "rf6",
                    "RawFile": "sample-a.raw",
                    "SampleLabel": "sample-a.raw [rf6]",
                    "Flagged": False,
                },
                {
                    "RunKey": "rf7",
                    "RawFile": "sample-b.raw",
                    "SampleLabel": "sample-b.raw [rf7]",
                    "Flagged": True,
                },
            ]
        )
        predictions = pd.DataFrame(
            {"Anomaly": [1, 0], "Anomaly_Score": [0.91, 0.12]},
            index=["rf6", "rf7"],
        )

        proposal = compute_flag_proposals(qc_data, predictions)

        self.assertEqual(proposal["run_keys_to_flag"], ["rf6"])
        self.assertEqual(proposal["run_keys_to_unflag"], ["rf7"])
        self.assertEqual(
            proposal["preview_rows"],
            [
                {
                    "run_key": "rf6",
                    "sample_label": "sample-a.raw [rf6]",
                    "raw_file": "sample-a.raw",
                    "action": "flag",
                    "current_flagged": False,
                },
                {
                    "run_key": "rf7",
                    "sample_label": "sample-b.raw [rf7]",
                    "raw_file": "sample-b.raw",
                    "action": "unflag",
                    "current_flagged": True,
                },
            ],
        )
        self.assertEqual(qc_data["Flagged"].tolist(), [False, True])

    @patch("dashboards.dashboards.dashboard.anomaly.T.set_rawfile_action")
    def test__apply_anomaly_flag_changes_applies_flag_and_unflag_actions(self, mock_action):
        mock_action.side_effect = [{"status": "success"}, {"status": "success"}]

        status, refresh = apply_anomaly_flag_changes(
            proposal={
                "project": "proj",
                "pipeline": "pipe",
                "run_keys_to_flag": ["rf1"],
                "run_keys_to_unflag": ["rf2"],
            },
            project="proj",
            pipeline="pipe",
            user=object(),
            n_clicks=1,
        )

        self.assertIn("Applied 2 anomaly flag change", status)
        self.assertIn('"project": "proj"', refresh)
        self.assertEqual(mock_action.call_count, 2)

    @patch("dashboards.dashboards.dashboard.anomaly.T.set_rawfile_action")
    def test__apply_anomaly_flag_changes_stops_on_first_mutation_failure(self, mock_action):
        mock_action.return_value = {"status": "boom"}

        status, refresh = apply_anomaly_flag_changes(
            proposal={
                "project": "proj",
                "pipeline": "pipe",
                "run_keys_to_flag": ["rf1"],
            },
            project="proj",
            pipeline="pipe",
            user=object(),
            n_clicks=1,
        )

        self.assertEqual(status, "boom")
        self.assertIs(refresh, dash.no_update)

    def test__update_kpis_uses_structured_scope_rows(self):
        result = update_kpis(
            {
                "rows": [
                    {
                        "RawFile": "a.raw",
                        "N_protein_groups": 100,
                        "N_peptides": 200,
                        "MS/MS Identified [%]": 55.0,
                    }
                ],
                "error": {"kind": "parsing", "message": "ignored by KPI summary"},
            },
            "proj",
            "pipe",
        )

        self.assertEqual(result[0], "1")
        self.assertEqual(result[1], "100.0")


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

    def test__set_rawfile_action_accept_and_reject_use_display_ref_for_uuid_prefixed_upload(self):
        raw_file = RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("DashboardAccept.RAW", b"..."),
            created_by=self.user,
        )
        RawFile.objects.filter(pk=raw_file.pk).update(
            orig_file=f"upload/{uuid4().hex}_DashboardAccept.RAW"
        )
        raw_file.refresh_from_db()

        response = set_rawfile_action(
            self.project.slug,
            self.pipeline.slug,
            [raw_file.display_ref],
            "accept",
            user=self.user,
        )
        self.assertEqual(response["status"], "success")
        raw_file.refresh_from_db()
        self.assertTrue(raw_file.use_downstream)

        response = set_rawfile_action(
            self.project.slug,
            self.pipeline.slug,
            [raw_file.display_ref],
            "reject",
            user=self.user,
        )
        self.assertEqual(response["status"], "success")
        raw_file.refresh_from_db()
        self.assertFalse(raw_file.use_downstream)

    @patch("dashboards.dashboards.dashboard.index.T.get_pipeline_uploaders")
    @patch("dashboards.dashboards.dashboard.index.T.get_qc_data")
    def test__refresh_qc_table_returns_visible_alert_for_backend_error(
        self,
        mock_get_qc_data,
        mock_get_pipeline_uploaders,
    ):
        mock_get_qc_data.return_value = {
            "status": "error",
            "data": None,
            "error": {
                "kind": "parsing",
                "message": "Dashboard data could not be parsed.",
                "detail": "QC data request error: bad parquet",
            },
        }
        mock_get_pipeline_uploaders.return_value = {"status": "no_data", "data": []}

        _table, scope_data, _uploaders, _scope_style, _scope_options, _refresh_probe, alert = refresh_qc_table(
            self.project.slug,
            self.pipeline.slug,
            "__all__",
            None,
            [],
            True,
            None,
            user=self.user,
        )

        self.assertEqual(scope_data["status"], "error")
        self.assertEqual(scope_data["error"]["kind"], "parsing")
        self.assertIsNotNone(alert)
