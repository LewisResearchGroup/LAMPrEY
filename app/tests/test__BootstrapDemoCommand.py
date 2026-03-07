from django.core.management import call_command
from django.test import TestCase

from maxquant.models import Pipeline, RawFile, Result
from project.models import Project
from user.models import User


class BootstrapDemoCommandTestCase(TestCase):
    def test_bootstrap_demo_creates_workspace_with_seeded_results(self):
        call_command("bootstrap_demo", user="user@email.com", with_results=True)

        self.user = User.objects.get(email="user@email.com")
        project = Project.objects.get(name="Demo Project")
        pipeline = Pipeline.objects.get(name="TMT QC Demo", project=project)
        raw_files = RawFile.objects.filter(pipeline=pipeline, created_by=self.user)
        results = Result.objects.filter(raw_file__pipeline=pipeline)

        self.assertTrue(project.users.filter(pk=self.user.pk).exists())
        self.assertEqual(raw_files.count(), 3)
        self.assertEqual(results.count(), 3)
        self.assertEqual(raw_files.filter(use_downstream=True).count(), 3)
        self.assertTrue(pipeline.mqpar_path.is_file())
        self.assertTrue(pipeline.fasta_path.is_file())
        self.assertTrue(results.first().output_dir_maxquant.is_dir())

    def test_bootstrap_demo_is_idempotent_without_force(self):
        call_command("bootstrap_demo", user="user@email.com", with_results=True)
        call_command("bootstrap_demo", user="user@email.com", with_results=True)

        self.user = User.objects.get(email="user@email.com")
        self.assertEqual(Project.objects.filter(name="Demo Project").count(), 1)
        self.assertEqual(Pipeline.objects.filter(name="TMT QC Demo").count(), 1)
        self.assertEqual(RawFile.objects.filter(created_by=self.user).count(), 3)
        self.assertEqual(Result.objects.count(), 3)
