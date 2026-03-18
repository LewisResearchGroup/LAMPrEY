from django.core.management.base import BaseCommand, CommandError

from maxquant.dashboard_cache import pipeline_dashboard_qc_data
from maxquant.models import Pipeline, Result


class Command(BaseCommand):
    help = "Rebuild per-run and pipeline dashboard QC caches."

    def add_arguments(self, parser):
        parser.add_argument("--project", help="Project slug to limit the rebuild scope.")
        parser.add_argument("--pipeline", help="Pipeline slug to limit the rebuild scope.")

    def handle(self, *args, **options):
        project_slug = options.get("project")
        pipeline_slug = options.get("pipeline")

        pipelines = Pipeline.objects.select_related("project").all().order_by("project__slug", "slug")
        if project_slug:
            pipelines = pipelines.filter(project__slug=project_slug)
        if pipeline_slug:
            pipelines = pipelines.filter(slug=pipeline_slug)

        pipelines = list(pipelines)
        if not pipelines:
            raise CommandError("No pipelines matched the requested scope.")

        total_results = 0
        for pipeline in pipelines:
            results = list(
                Result.objects.filter(raw_file__pipeline=pipeline)
                .select_related("raw_file__pipeline__project")
                .order_by("raw_file__created", "raw_file_id")
            )
            self.stdout.write(
                f"Rebuilding dashboard QC caches for {pipeline.project.slug}/{pipeline.slug} ({len(results)} runs)"
            )
            for result in results:
                result.dashboard_qc_data(force_update=True)
                total_results += 1
            pipeline_dashboard_qc_data(pipeline, force_update=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Rebuilt dashboard QC caches for {len(pipelines)} pipeline(s) and {total_results} run cache(s)."
            )
        )
