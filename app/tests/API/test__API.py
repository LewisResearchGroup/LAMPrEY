from django.test import TestCase
from datetime import date
from unittest.mock import patch
from project.models import Project
from maxquant.models import Pipeline

from maxquant.models import RawFile


from django.core.files.uploadedfile import SimpleUploadedFile


from django.test import Client
from user.models import User
from api.views import get_protein_quant_fn

URL = "http://localhost:8000"


class ApiTestCase(TestCase):
    def setUp(self):
        if not hasattr(self, "pipeline"):
            print("Setup")
            self.user = User.objects.create_user(
                email="api-user@example.com",
                password="testpass123",
            )
            self.project = Project.objects.create(
                name="project", description="A test project", created_by=self.user
            )
            self.project.users.add(self.user)

            contents_mqpar = b"<mqpar></mqpar>"
            contents_fasta = b">protein\nSEQUENCE"

            self.pipeline = Pipeline.objects.create(
                name="pipe",
                project=self.project,
                created_by=self.user,
                fasta_file=SimpleUploadedFile("my_fasta.fasta", contents_fasta),
                mqpar_file=SimpleUploadedFile("my_mqpar.xml", contents_mqpar),
                rawtools_args="-p -q -x -u -l -m -r TMT11 -chro 12TB",
            )

            self.raw_file = RawFile.objects.create(
                pipeline=self.pipeline,
                orig_file=SimpleUploadedFile("fake.raw", b"..."),
                created_by=self.user,
            )

    def test__projects(self):
        c = Client()
        c.force_login(self.user)
        url = f"{URL}/api/projects"
        actual = c.post(
            url,
            data={"uid": self.user.uuid},
            content_type="application/json",
        ).json()
        expected = [
            {
                "pk": self.project.pk,
                "name": "project",
                "description": "A test project",
                "slug": "project",
            }
        ]
        assert actual == expected, actual

    def test__projects_unauthenticated(self):
        """Verify that unauthenticated requests are rejected."""
        c = Client()
        url = f"{URL}/api/projects"
        response = c.post(url)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__pipelines(self):
        """Test pipeline list endpoint."""
        c = Client()
        c.force_login(self.user)
        url = f"{URL}/api/pipelines"
        response = c.post(url, {"project": "project"}, content_type="application/json")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "pipe"

    def test__pipelines_unauthenticated(self):
        """Verify unauthenticated pipeline requests are rejected."""
        c = Client()
        url = f"{URL}/api/pipelines"
        response = c.post(url, {"project": "project"}, content_type="application/json")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__create_flag_requires_auth(self):
        """Verify flag creation requires authentication."""
        c = Client()
        url = f"{URL}/api/flag/create"
        response = c.post(url, {
            "project": "project",
            "pipeline": "pipe",
            "raw_files": ["fake.raw"],
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__create_flag_requires_project_membership(self):
        """Verify users can only flag files in their projects."""
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
        )
        c = Client()
        c.force_login(other_user)
        url = f"{URL}/api/flag/create"
        response = c.post(url, {
            "project": "project",
            "pipeline": "pipe",
            "raw_files": ["fake.raw"],
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__delete_flag_requires_auth(self):
        """Verify flag deletion requires authentication."""
        c = Client()
        url = f"{URL}/api/flag/delete"
        response = c.post(url, {
            "project": "project",
            "pipeline": "pipe",
            "raw_files": ["fake.raw"],
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__rawfile_requires_auth(self):
        """Verify rawfile endpoint requires authentication."""
        c = Client()
        url = f"{URL}/api/rawfile"
        response = c.post(url, {
            "project": "project",
            "pipeline": "pipe",
            "action": "flag",
            "raw_files": ["fake.raw"],
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

    def test__get_protein_quant_fn_data_range_limits_results(self):
        RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("fake-1.raw", b"..."),
            created_by=self.user,
            created=date(2024, 1, 1),
        )
        RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("fake-2.raw", b"..."),
            created_by=self.user,
            created=date(2024, 1, 2),
        )
        RawFile.objects.create(
            pipeline=self.pipeline,
            orig_file=SimpleUploadedFile("fake-3.raw", b"..."),
            created_by=self.user,
            created=date(2024, 1, 3),
        )

        with patch(
            "maxquant.Result.Result.create_protein_quant",
            side_effect=lambda: "protein_quant.parquet",
        ):
            fns = get_protein_quant_fn(
                self.project.slug,
                self.pipeline.slug,
                data_range=2,
                user=self.user,
            )

        assert len(fns) == 2, fns
