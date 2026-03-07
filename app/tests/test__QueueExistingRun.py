from unittest.mock import patch

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
