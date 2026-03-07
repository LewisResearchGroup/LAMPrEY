import os
import signal
import subprocess
import sys

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from unittest.mock import patch

from maxquant.models import Pipeline, RawFile, Result
from project.models import Project
from user.models import User


class ResultCancellationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tester-cancel@example.com", password="pass1234"
        )
        self.project = Project.objects.create(
            name="Cancel Project",
            description="Cancellation test project",
            created_by=self.user,
        )
        self.contents_mqpar = b"<mqpar></mqpar>"
        self.contents_fasta = b">protein\nSEQUENCE"

    def _make_result(self, pipeline_name, raw_name):
        pipeline = Pipeline.objects.create(
            name=pipeline_name,
            project=self.project,
            created_by=self.user,
            fasta_file=SimpleUploadedFile(f"{pipeline_name}.fasta", self.contents_fasta),
            mqpar_file=SimpleUploadedFile(f"{pipeline_name}.xml", self.contents_mqpar),
            rawtools_args="-p -q -x",
        )
        raw_file = RawFile.objects.create(
            pipeline=pipeline,
            orig_file=SimpleUploadedFile(raw_name, b"..."),
            created_by=self.user,
        )
        return Result.objects.get(raw_file=raw_file)

    def _start_marker_process(self, marker):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", marker],
            preexec_fn=os.setsid,
        )
        self.addCleanup(self._terminate_process, proc)
        return proc

    def _terminate_process(self, proc):
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)

    @patch("maxquant.Result.current_app.control.revoke")
    def test_cancel_only_kills_tracked_group_with_overlapping_filenames(self, _revoke):
        target = self._make_result("pipe-a", "shared.raw")
        other = self._make_result("pipe-b", "shared.raw")

        target_proc = self._start_marker_process("shared.raw")
        other_proc = self._start_marker_process("shared.raw")
        stray_proc = self._start_marker_process("shared.raw")

        target.maxquant_pid = target_proc.pid
        target.maxquant_pgid = os.getpgid(target_proc.pid)
        target.save(update_fields=["maxquant_pid", "maxquant_pgid"])

        other.maxquant_pid = other_proc.pid
        other.maxquant_pgid = os.getpgid(other_proc.pid)
        other.save(update_fields=["maxquant_pid", "maxquant_pgid"])

        target.cancel_active_jobs()

        target_proc.wait(timeout=5)
        self.assertIsNotNone(target_proc.returncode)
        self.assertIsNone(other_proc.poll())
        self.assertIsNone(stray_proc.poll())

        target.refresh_from_db()
        self.assertIsNotNone(target.cancel_requested_at)
        self.assertIsNone(target.maxquant_pid)
        self.assertIsNone(target.maxquant_pgid)

    @patch("maxquant.Result.current_app.control.revoke")
    def test_cancel_can_resolve_process_group_from_exact_pid(self, _revoke):
        target = self._make_result("pipe-c", "shared.raw")
        target_proc = self._start_marker_process("shared.raw")

        target.maxquant_pid = target_proc.pid
        target.maxquant_pgid = None
        target.save(update_fields=["maxquant_pid", "maxquant_pgid"])

        target.cancel_active_jobs()

        target_proc.wait(timeout=5)
        self.assertIsNotNone(target_proc.returncode)

        target.refresh_from_db()
        self.assertIsNone(target.maxquant_pid)
        self.assertIsNone(target.maxquant_pgid)
