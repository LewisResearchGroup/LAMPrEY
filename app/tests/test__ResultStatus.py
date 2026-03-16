from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
import pandas as pd

from maxquant.models import Pipeline, RawFile, Result
from project.models import Project
from user.models import User


class ResultStatusTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tester-status@example.com", password="pass1234"
        )
        self.project = Project.objects.create(
            name="Status Project", description="Status test project", created_by=self.user
        )
        contents_mqpar = b"<mqpar></mqpar>"
        contents_fasta = b">protein\nSEQUENCE"
        self.pipeline = Pipeline.objects.create(
            name="status-pipe",
            project=self.project,
            created_by=self.user,
            fasta_file=SimpleUploadedFile("status_fasta.fasta", contents_fasta),
            mqpar_file=SimpleUploadedFile("status_mqpar.xml", contents_mqpar),
            rawtools_args="-p -q -x",
        )
        self.raw_file = RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("status_case.raw", b"..."),
            created_by=self.user,
        )
        self.result = Result.objects.get(raw_file=self.raw_file)

    def _write_file(self, fn, text):
        fn = Path(fn)
        fn.parent.mkdir(parents=True, exist_ok=True)
        fn.write_text(text, encoding="utf-8")

    def test_maxquant_error_overrides_done_marker(self):
        # Mark RawTools stages as done so overall status depends on MaxQuant.
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")

        # MaxQuant wrote time.txt but also a non-empty error file.
        self._write_file(self.result.output_dir_maxquant / "time.txt", "00:05.00")
        self._write_file(
            self.result.output_dir_maxquant / "maxquant.err",
            "System.Exception: Your fully qualified path of raw file is too long.",
        )

        self.assertEqual(self.result.maxquant_status, "failed")
        self.assertEqual(self.result.overall_status, "failed")

    def test_rawtools_metrics_error_overrides_done_markers(self):
        # Mark MaxQuant and RawTools QC as done so overall status depends on RawTools metrics.
        self._write_file(self.result.output_dir_maxquant / "time.txt", "00:05.00")
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")

        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools / "rawtools_metrics.err",
            "RawTools metrics failed",
        )

        self.assertEqual(self.result.rawtools_metrics_status, "failed")
        self.assertEqual(self.result.overall_status, "failed")

    def test_rawtools_qc_error_overrides_done_marker(self):
        # Mark MaxQuant and RawTools metrics as done so overall status depends on RawTools QC.
        self._write_file(self.result.output_dir_maxquant / "time.txt", "00:05.00")
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )

        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")
        self._write_file(
            self.result.output_dir_rawtools_qc / "rawtools_qc.err",
            "RawTools QC failed",
        )

        self.assertEqual(self.result.rawtools_qc_status, "failed")
        self.assertEqual(self.result.overall_status, "failed")

    @patch.object(Result, "_task_state", return_value="SUCCESS")
    def test_rawtools_success_state_with_outputs_is_done(self, _mock_task_state):
        self.result.rawtools_metrics_task_id = "fake-metrics-task"
        self.result.rawtools_qc_task_id = "fake-qc-task"
        self.result.save(
            update_fields=["rawtools_metrics_task_id", "rawtools_qc_task_id"]
        )

        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")
        self._write_file(self.result.output_dir_rawtools / "rawtools_metrics.err", "")
        self._write_file(self.result.output_dir_rawtools_qc / "rawtools_qc.err", "")

        self.assertEqual(self.result.rawtools_metrics_status, "done")
        self.assertEqual(self.result.rawtools_qc_status, "done")

    @patch.object(Result, "_task_state", return_value="PENDING")
    def test_rawtools_pending_state_with_outputs_is_done(self, _mock_task_state):
        self.result.rawtools_metrics_task_id = "fake-metrics-task"
        self.result.rawtools_qc_task_id = "fake-qc-task"
        self.result.save(
            update_fields=["rawtools_metrics_task_id", "rawtools_qc_task_id"]
        )

        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")

        self.assertEqual(self.result.rawtools_metrics_status, "done")
        self.assertEqual(self.result.rawtools_qc_status, "done")

    def test_maxquant_success_phrase_in_out_file_marks_done_first(self):
        # RawTools done so overall depends on MaxQuant.
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")

        # Strong success indicator in maxquant.out should win.
        self._write_file(
            self.result.output_dir_maxquant / "maxquant.out",
            "...\nFinish writing tables\n...",
        )
        self._write_file(
            self.result.output_dir_maxquant / "maxquant.err",
            "error text that would otherwise mark failed",
        )

        self.assertEqual(self.result.maxquant_status, "done")
        self.assertEqual(self.result.overall_status, "done")

    def test_maxquant_fatal_error_markers_override_success_phrase(self):
        # RawTools done so overall depends on MaxQuant.
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")

        self._write_file(
            self.result.output_dir_maxquant / "maxquant.out",
            "...\nFinish writing tables\n...",
        )
        self._write_file(
            self.result.output_dir_maxquant / "maxquant.err",
            "System.Exception: path too long",
        )

        self.assertEqual(self.result.maxquant_status, "failed")
        self.assertEqual(self.result.overall_status, "failed")

    def test_stage_error_details_exposes_failed_stage_excerpt(self):
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")
        self._write_file(
            self.result.output_dir_maxquant / "maxquant.err",
            "Unhandled Exception:\nSystem.Exception: Your fully qualified path of raw file is too long.",
        )

        details = self.result.stage_error_details
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["stage"], "maxquant")
        self.assertIn("Unhandled Exception", details[0]["message"])

    def test_create_protein_quant_schema_parse_error_marks_maxquant_failed(self):
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(
            self.result.output_dir_rawtools
            / f"{self.raw_file.name}_Ms2_TIC_chromatogram.txt",
            "ok",
        )
        self._write_file(self.result.output_dir_rawtools_qc / "QcDataTable.csv", "ok")
        self._write_file(self.result.output_dir_maxquant / "time.txt", "00:05.00")
        self._write_file(
            self.result.output_dir_maxquant / "proteinGroups.txt",
            "\t".join(
                [
                    "Majority protein IDs",
                    "Fasta headers",
                    "Intensity",
                    "Reporter intensity corrected 1 sample",
                ]
            )
            + "\n"
            + "\t".join(["P1", "header-1", "1000", "10"])
            + "\n",
        )

        actual = self.result.create_protein_quant()

        self.assertIsNone(actual)
        self.assertEqual(self.result.maxquant_status, "failed")
        self.assertEqual(self.result.overall_status, "failed")
        self.assertIn(
            "MaxQuant parse error",
            (self.result.output_dir_maxquant / "maxquant.err").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn("missing required columns", self.result.stage_error_details[0]["message"])

    @patch("maxquant.Result.rawtools_qc.delay")
    @patch("maxquant.Result.rawtools_metrics.delay")
    def test_rawtools_rerun_flag_is_forwarded_to_tasks(
        self, mock_metrics_delay, mock_qc_delay
    ):
        mock_metrics_delay.return_value = SimpleNamespace(id="metrics-task")
        mock_qc_delay.return_value = SimpleNamespace(id="qc-task")

        self.result.run_rawtools_metrics(rerun=True)
        self.result.run_rawtools_qc(rerun=True)

        self.assertEqual(mock_metrics_delay.call_count, 1)
        self.assertEqual(mock_qc_delay.call_count, 1)
        self.assertTrue(mock_metrics_delay.call_args.kwargs["rerun"])
        self.assertTrue(mock_qc_delay.call_args.kwargs["rerun"])

    def test_dashboard_qc_data_uses_cache_when_fresh(self):
        raw_df = pd.DataFrame(
            [{"RawFile": self.raw_file.name, "DateAcquired": pd.Timestamp("2024-01-01"), "MetricA": 1.0}]
        )
        mq_df = pd.DataFrame([{"RawFile": self.raw_file.name, "MetricB": 2.0}])

        with patch.object(Result, "rawtools_qc_data", return_value=raw_df) as mock_rt:
            with patch.object(Result, "maxquant_qc_data", return_value=mq_df) as mock_mq:
                first = self.result.dashboard_qc_data(force_update=True)

        self.assertEqual(mock_rt.call_count, 1)
        self.assertEqual(mock_mq.call_count, 1)
        self.assertTrue(self.result.dashboard_qc_cache_path.is_file())
        self.assertEqual(first.loc[0, "MetricA"], 1.0)
        self.assertEqual(first.loc[0, "MetricB"], 2.0)

        with patch.object(Result, "rawtools_qc_data", side_effect=AssertionError("should use cache")):
            with patch.object(Result, "maxquant_qc_data", side_effect=AssertionError("should use cache")):
                second = self.result.dashboard_qc_data()

        self.assertEqual(second.loc[0, "MetricA"], 1.0)
        self.assertEqual(second.loc[0, "MetricB"], 2.0)

    def test_dashboard_qc_data_refreshes_when_source_is_newer_than_cache(self):
        initial_raw_df = pd.DataFrame(
            [{"RawFile": self.raw_file.name, "DateAcquired": pd.Timestamp("2024-01-01"), "MetricA": 1.0}]
        )
        initial_mq_df = pd.DataFrame([{"RawFile": self.raw_file.name, "MetricB": 2.0}])
        updated_raw_df = pd.DataFrame(
            [{"RawFile": self.raw_file.name, "DateAcquired": pd.Timestamp("2024-01-01"), "MetricA": 10.0}]
        )
        updated_mq_df = pd.DataFrame([{"RawFile": self.raw_file.name, "MetricB": 20.0}])

        with patch.object(Result, "rawtools_qc_data", return_value=initial_raw_df):
            with patch.object(Result, "maxquant_qc_data", return_value=initial_mq_df):
                self.result.dashboard_qc_data(force_update=True)

        source_path = self.result.output_dir_rawtools_qc / "QcDataTable.csv"
        self._write_file(source_path, "updated")
        future_time = self.result.dashboard_qc_cache_path.stat().st_mtime + 5
        os.utime(source_path, (future_time, future_time))

        with patch.object(Result, "rawtools_qc_data", return_value=updated_raw_df) as mock_rt:
            with patch.object(Result, "maxquant_qc_data", return_value=updated_mq_df) as mock_mq:
                refreshed = self.result.dashboard_qc_data()

        self.assertEqual(mock_rt.call_count, 1)
        self.assertEqual(mock_mq.call_count, 1)
        self.assertEqual(refreshed.loc[0, "MetricA"], 10.0)
        self.assertEqual(refreshed.loc[0, "MetricB"], 20.0)
