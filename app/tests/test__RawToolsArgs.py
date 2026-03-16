from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from maxquant.models import Pipeline
from maxquant.rawtools import DEFAULT_RAWTOOLS_ARGS, normalize_rawtools_args, parse_rawtools_args
from maxquant.tasks import rawtools_metrics
from omics.proteomics.rawtools.quality_control import (
    rawtools_metrics_cmd,
    rawtools_output_files_exist,
)
from project.models import Project
from user.models import User


class RawToolsArgsParsingTestCase(SimpleTestCase):
    def test_default_args_skip_reporter_quantification(self):
        parsed = parse_rawtools_args(DEFAULT_RAWTOOLS_ARGS)

        self.assertEqual(parsed, ["-p", "-x", "-u", "-l", "-m", "-chro", "12TB"])

    def test_parse_allows_quoted_values_with_spaces(self):
        parsed = parse_rawtools_args('-q -r "TMT 11" -chro "12 TB"')

        self.assertEqual(parsed, ["-q", "-r", "TMT 11", "-chro", "12 TB"])

    def test_parse_rejects_shell_metacharacters(self):
        with self.assertRaises(ValidationError):
            parse_rawtools_args('-q -r "TMT11; touch /tmp/pwned"')

    def test_parse_rejects_unsupported_tokens(self):
        with self.assertRaises(ValidationError):
            parse_rawtools_args("-q --help")

    def test_normalize_preserves_safe_spacing(self):
        normalized = normalize_rawtools_args('  -q   -r   "TMT 11"  ')

        self.assertEqual(normalized, "-q -r 'TMT 11'")


class RawToolsArgsModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tester-rawtools@example.com", password="pass1234"
        )
        self.project = Project.objects.create(
            name="RawTools Project",
            description="RawTools parser tests",
            created_by=self.user,
        )
        self.contents_mqpar = b"<mqpar></mqpar>"
        self.contents_fasta = b">protein\nSEQUENCE"

    def test_pipeline_save_normalizes_rawtools_args(self):
        pipeline = Pipeline.objects.create(
            name="rawtools-pipe",
            project=self.project,
            created_by=self.user,
            fasta_file=SimpleUploadedFile("rawtools.fasta", self.contents_fasta),
            mqpar_file=SimpleUploadedFile("rawtools.xml", self.contents_mqpar),
            rawtools_args='-q -r "TMT 11"',
        )

        self.assertEqual(pipeline.rawtools_args, "-q -r 'TMT 11'")
        self.assertEqual(pipeline.rawtools_args_list, ["-q", "-r", "TMT 11"])

    def test_pipeline_full_clean_rejects_invalid_rawtools_args(self):
        pipeline = Pipeline(
            name="rawtools-invalid-pipe",
            project=self.project,
            created_by=self.user,
            rawtools_args='-q -r "TMT11; rm -rf /"',
        )

        with self.assertRaises(ValidationError):
            pipeline.full_clean()


class RawToolsTaskExecutionTestCase(SimpleTestCase):
    def test_rawtools_metrics_cmd_uses_metrics_file_as_completion_sentinel(self):
        with TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "sample.raw"
            output_dir = Path(tmpdir) / "out"
            raw.write_text("raw", encoding="utf-8")

            self.assertIsNotNone(rawtools_metrics_cmd(str(raw), str(output_dir)))

            output_dir.mkdir(exist_ok=True)
            (output_dir / "sample.raw_Metrics.txt").write_text("ok", encoding="utf-8")

            self.assertIsNone(rawtools_metrics_cmd(str(raw), str(output_dir)))

    def test_rawtools_output_files_exist_does_not_require_matrix_output(self):
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            raw = output_dir / "sample.raw"
            raw.write_text("raw", encoding="utf-8")
            (output_dir / "sample.raw.mgf").write_text("mgf", encoding="utf-8")
            (output_dir / "sample.raw_Metrics.txt").write_text("metrics", encoding="utf-8")
            (output_dir / "sample.raw_Ms2_TIC_chromatogram.txt").write_text(
                "tic", encoding="utf-8"
            )

            self.assertTrue(rawtools_output_files_exist(str(output_dir)))

    @patch("maxquant.tasks._run_cancelable_process")
    @patch("maxquant.tasks._defer_if_busy")
    @patch("maxquant.tasks._is_canceled_result", side_effect=[False, False])
    def test_rawtools_metrics_uses_explicit_argv(
        self, _is_canceled, _defer_if_busy, mock_run
    ):
        with TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "sample.raw"
            output_dir = Path(tmpdir) / "out"
            raw.write_text("raw", encoding="utf-8")

            rawtools_metrics.run(
                str(raw),
                str(output_dir),
                arguments='-q -r "TMT 11"',
                rerun=True,
                result_id=123,
            )

        self.assertEqual(mock_run.call_count, 1)
        argv = mock_run.call_args.args[0]
        self.assertEqual(argv[:5], ["/opt/conda/bin/rawtools.sh", "-f", str(raw), "-o", str(output_dir)])
        self.assertEqual(argv[5:], ["-q", "-r", "TMT 11"])
        self.assertFalse(mock_run.call_args.kwargs.get("shell", False))
        self.assertEqual(mock_run.call_args.kwargs["cwd"], str(output_dir))
        self.assertTrue(mock_run.call_args.kwargs["stdout_path"].endswith("rawtools_metrics.out"))
        self.assertTrue(mock_run.call_args.kwargs["stderr_path"].endswith("rawtools_metrics.err"))

    @patch("maxquant.tasks._run_cancelable_process")
    @patch("maxquant.tasks._defer_if_busy")
    @patch("maxquant.tasks._is_canceled_result", side_effect=[False, False])
    def test_rawtools_metrics_rejects_invalid_shell_tokens(
        self, _is_canceled, _defer_if_busy, mock_run
    ):
        with TemporaryDirectory() as tmpdir:
            raw = Path(tmpdir) / "sample.raw"
            output_dir = Path(tmpdir) / "out"
            raw.write_text("raw", encoding="utf-8")

            with self.assertRaises(ValidationError):
                rawtools_metrics.run(
                    str(raw),
                    str(output_dir),
                    arguments='-q "; touch /tmp/pwned"',
                    rerun=True,
                    result_id=123,
                )

        self.assertEqual(mock_run.call_count, 0)
