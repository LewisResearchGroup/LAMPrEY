from unittest.mock import PropertyMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from maxquant.models import Pipeline, RawFile, Result
from project.models import Project
from user.models import User


class QueueExistingRunTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tester-requeue@example.com", password="pass1234"
        )
        self.project = Project.objects.create(
            name="Queue Project",
            description="Queue test project",
            created_by=self.user,
        )
        contents_mqpar = b"<mqpar></mqpar>"
        contents_fasta = b">protein\nSEQUENCE"
        self.pipeline = Pipeline.objects.create(
            name="queue-pipe",
            project=self.project,
            created_by=self.user,
            fasta_file=SimpleUploadedFile("queue.fasta", contents_fasta),
            mqpar_file=SimpleUploadedFile("queue.xml", contents_mqpar),
            rawtools_args="-p -q -x",
        )
        with patch.object(Result, "run"):
            self.raw_file = RawFile.objects.create(
                pipeline=self.pipeline,
                orig_file=SimpleUploadedFile("queue.raw", b"..."),
                created_by=self.user,
            )
        self.result = Result.objects.get(raw_file=self.raw_file)
        self.client.force_login(self.user)

    @patch.object(Result, "run_rawtools_qc")
    @patch.object(Result, "run_rawtools_metrics")
    @patch.object(Result, "run_maxquant")
    def test_queue_existing_run_is_atomic_and_dispatches_once(
        self,
        mock_run_maxquant,
        mock_run_rawtools_metrics,
        mock_run_rawtools_qc,
    ):
        url = reverse("maxquant:queue_existing_run", kwargs={"pk": self.result.pk})

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")

        self.result.refresh_from_db()
        self.assertEqual(self.result.processing_attempt, 1)
        self.assertIsNone(self.result.requeue_dispatch_started_at)
        self.assertEqual(mock_run_maxquant.call_count, 1)
        self.assertEqual(mock_run_rawtools_metrics.call_count, 1)
        self.assertEqual(mock_run_rawtools_qc.call_count, 1)
        self.assertTrue(mock_run_maxquant.call_args.kwargs["rerun"])
        self.assertTrue(mock_run_rawtools_metrics.call_args.kwargs["rerun"])
        self.assertTrue(mock_run_rawtools_qc.call_args.kwargs["rerun"])
        self.assertFalse(self.result.has_active_dispatch)

    def test_queue_existing_run_rejects_duplicate_submission_when_marker_exists(self):
        self.result.requeue_dispatch_started_at = timezone.now()
        self.result.save(update_fields=["requeue_dispatch_started_at"])

        response = self.client.post(
            reverse("maxquant:queue_existing_run", kwargs={"pk": self.result.pk})
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "Run is already queued or running.")

    def test_requeue_dispatch_marker_reports_run_as_queued(self):
        self.result.requeue_dispatch_started_at = timezone.now()
        self.result.save(update_fields=["requeue_dispatch_started_at"])
        self.result.refresh_from_db()

        self.assertEqual(self.result.maxquant_status, "queued")
        self.assertEqual(self.result.rawtools_metrics_status, "queued")
        self.assertEqual(self.result.rawtools_qc_status, "queued")
        self.assertEqual(self.result.overall_status, "queued")
        self.assertTrue(self.result.has_active_stage)

    @patch.object(Result, "run_rawtools_qc")
    @patch.object(Result, "run_rawtools_metrics")
    @patch.object(Result, "run_maxquant")
    def test_queue_existing_run_ignores_recent_output_activity_without_dispatch_markers(
        self,
        mock_run_maxquant,
        mock_run_rawtools_metrics,
        mock_run_rawtools_qc,
    ):
        self.result.refresh_from_db()

        self.assertFalse(self.result.has_active_dispatch)

        with patch.object(
            Result,
            "has_active_stage",
            new_callable=PropertyMock,
            return_value=True,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("maxquant:queue_existing_run", kwargs={"pk": self.result.pk})
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_run_maxquant.call_count, 1)
        self.assertEqual(mock_run_rawtools_metrics.call_count, 1)
        self.assertEqual(mock_run_rawtools_qc.call_count, 1)


class ResultAutoRunSignalTestCase(TestCase):
    @patch.object(Result, "run")
    def test_result_auto_runs_when_pipeline_is_manual(self, mock_run):
        user = User.objects.create_user(
            email="manual-run@example.com", password="pass1234"
        )
        project = Project.objects.create(
            name="Manual Queue Project",
            description="Manual queue test project",
            created_by=user,
        )
        pipeline = Pipeline.objects.create(
            name="manual-queue-pipe",
            project=project,
            created_by=user,
            run_automatically=False,
            fasta_file=SimpleUploadedFile("manual.fasta", b">protein\nSEQUENCE"),
            mqpar_file=SimpleUploadedFile("manual.xml", b"<mqpar></mqpar>"),
            rawtools_args="-p -q -x",
        )

        RawFile.objects.create(
            pipeline=pipeline,
            orig_file=SimpleUploadedFile("manual.raw", b"..."),
            created_by=user,
        )

        mock_run.assert_called_once()

    @patch.object(Result, "run")
    def test_result_auto_runs_when_pipeline_is_automatic(self, mock_run):
        user = User.objects.create_user(
            email="auto-run@example.com", password="pass1234"
        )
        project = Project.objects.create(
            name="Auto Queue Project",
            description="Auto queue test project",
            created_by=user,
        )
        pipeline = Pipeline.objects.create(
            name="auto-queue-pipe",
            project=project,
            created_by=user,
            run_automatically=True,
            fasta_file=SimpleUploadedFile("auto.fasta", b">protein\nSEQUENCE"),
            mqpar_file=SimpleUploadedFile("auto.xml", b"<mqpar></mqpar>"),
            rawtools_args="-p -q -x",
        )

        RawFile.objects.create(
            pipeline=pipeline,
            orig_file=SimpleUploadedFile("auto.raw", b"..."),
            created_by=user,
        )

        mock_run.assert_called_once()

    @patch.object(Result, "run")
    def test_demo_result_does_not_auto_run(self, mock_run):
        user = User.objects.create_user(
            email="demo-run@example.com", password="pass1234"
        )
        project = Project.objects.create(
            name="Demo Queue Project",
            description="Demo queue test project",
            created_by=user,
        )
        pipeline = Pipeline.objects.create(
            name="demo-queue-pipe",
            project=project,
            created_by=user,
            run_automatically=False,
            fasta_file=SimpleUploadedFile("demo.fasta", b">protein\nSEQUENCE"),
            mqpar_file=SimpleUploadedFile("demo.xml", b"<mqpar></mqpar>"),
            rawtools_args="-p -q -x",
        )

        raw_file = RawFile(
            pipeline=pipeline,
            orig_file=SimpleUploadedFile("demo.raw", b"..."),
            created_by=user,
        )
        raw_file._skip_auto_result = True
        raw_file.save()

        Result.objects.create(raw_file=raw_file, input_source="demo", created_by=user)

        mock_run.assert_not_called()
