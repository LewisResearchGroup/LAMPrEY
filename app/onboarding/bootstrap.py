from __future__ import annotations

import json
import secrets
import shutil
from dataclasses import dataclass
import re
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from maxquant.models import Pipeline, RawFile, Result
from maxquant.rawtools import DEFAULT_RAWTOOLS_ARGS
from project.models import Project
from user.models import User


DEMO_PROJECT_NAME = "Demo Project"
DEMO_PIPELINE_NAME = "TMT QC Demo"
DEMO_RAW_FILENAMES = (
    "DEMO_01.raw",
    "DEMO_02.raw",
    "DEMO_03.raw",
)
UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{32}_(?=.+)", re.IGNORECASE)


@dataclass
class DemoBootstrapResult:
    user: User
    project: Project
    pipeline: Pipeline
    raw_files: list[RawFile]
    results: list[Result]
    created_user: bool
    created_project: bool
    created_pipeline: bool
    generated_password: str | None


def _first_existing_path(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(str(candidates[0]))


def _app_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _repo_root() -> Path:
    return _app_root().parent


def _compute_root() -> Path:
    return _repo_root() / "data" / "compute"


def _demo_seed_root() -> Path:
    return _repo_root() / "app" / "seed" / "demo"


def _demo_seed_manifest_path() -> Path:
    return _demo_seed_root() / "manifest.json"


def _demo_seed_config_dir() -> Path:
    return _demo_seed_root() / "config"


def _omics_test_data_root() -> Path:
    return _app_root() / "tests" / "omics" / "data"


def _seed_mqpar_path() -> Path:
    return _first_existing_path(
        _demo_seed_config_dir() / "mqpar.xml",
        _omics_test_data_root() / "maxquant" / "tmt11" / "mqpar" / "mqpar.xml",
        _app_root() / "seed" / "defaults" / "config" / "mqpar_2.4.12.0.xml",
    )


def _seed_fasta_path() -> Path:
    return _first_existing_path(
        _demo_seed_config_dir() / "fasta.faa",
        _demo_seed_root() / "config" / "fasta.faa",
    )


def _seed_maxquant_output_dir() -> Path:
    return _first_existing_path(
        _omics_test_data_root() / "maxquant" / "tmt11" / "example-0",
    )


def _seed_rawtools_dir() -> Path:
    return _first_existing_path(
        _omics_test_data_root() / "rawtools",
    )


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _logical_raw_name(filename: str) -> str:
    return UUID_PREFIX_RE.sub("", Path(filename).name)


def _demo_seed_specs():
    manifest_path = _demo_seed_manifest_path()
    if not manifest_path.is_file():
        return [{"filename": name, "source_output_dir": None} for name in DEMO_RAW_FILENAMES]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = []
    for run in manifest.get("runs", []):
        seed_dir = _demo_seed_root() / "runs" / run["seed_dir"]
        specs.append(
            {
                "filename": _logical_raw_name(run["filename"]),
                "source_output_dir": seed_dir if seed_dir.is_dir() else None,
            }
        )
    return specs or [{"filename": name, "source_output_dir": None} for name in DEMO_RAW_FILENAMES]


def _upsert_user(user_email: str, password: str | None = None) -> tuple[User, bool, str | None]:
    user = User.objects.filter(email=user_email).first()
    if user is not None:
        return user, False, None

    generated_password = password or secrets.token_urlsafe(12)
    user = User.objects.create_user(
        email=user_email,
        password=generated_password,
    )
    return user, True, generated_password


def _upsert_project(user: User, project_name: str) -> tuple[Project, bool]:
    project = Project.objects.filter(name=project_name).first()
    created = False
    if project is None:
        project = Project.objects.create(
            name=project_name,
            description="Seeded demo project for first-run onboarding.",
            created_by=user,
        )
        created = True
    if not project.users.filter(pk=user.pk).exists():
        project.users.add(user)
    return project, created


def _sync_pipeline_config(pipeline: Pipeline) -> None:
    maxquant_seed = _seed_mqpar_path()
    fasta_seed = _seed_fasta_path()

    pipeline.mqpar_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline.fasta_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(maxquant_seed, pipeline.mqpar_path)
    shutil.copy2(fasta_seed, pipeline.fasta_path)


def _upsert_pipeline(user: User, project: Project, pipeline_name: str) -> tuple[Pipeline, bool]:
    pipeline = Pipeline.objects.filter(project=project, name=pipeline_name).first()
    created = False
    if pipeline is None:
        pipeline = Pipeline.objects.create(
            name=pipeline_name,
            project=project,
            created_by=user,
            description="Seeded demo pipeline for first-run onboarding.",
            fasta_file=SimpleUploadedFile(
                _seed_fasta_path().name,
                _read_bytes(_seed_fasta_path()),
            ),
            mqpar_file=SimpleUploadedFile(
                _seed_mqpar_path().name,
                _read_bytes(_seed_mqpar_path()),
            ),
            rawtools_args=DEFAULT_RAWTOOLS_ARGS,
        )
        created = True
    else:
        _sync_pipeline_config(pipeline)
    return pipeline, created


def _delete_demo_runs(pipeline: Pipeline, user: User, demo_filenames) -> None:
    expected_names = set(demo_filenames)
    for raw_file in RawFile.objects.filter(pipeline=pipeline, created_by=user):
        if raw_file.logical_name not in expected_names:
            continue
        raw_file.delete()


def _delete_demo_temp_run_dirs(demo_filenames) -> None:
    maxquant_tmp_root = _compute_root() / "tmp" / "MaxQuant"
    if not maxquant_tmp_root.is_dir():
        return
    for filename in demo_filenames:
        for path in maxquant_tmp_root.glob(f"{filename}__rf*"):
            shutil.rmtree(path, ignore_errors=True)


def _reset_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _write_demo_chromatogram(target: Path, *, multiplier: int) -> None:
    lines = ["RetentionTime\tIntensity"]
    for minute in range(0, 91):
        center_a = 18 + multiplier
        center_b = 52 + multiplier
        center_c = 74 + multiplier
        intensity = (
            max(0, 140000 - abs(minute - center_a) * 8000)
            + max(0, 220000 - abs(minute - center_b) * 9000)
            + max(0, 120000 - abs(minute - center_c) * 7000)
        )
        lines.append(f"{minute}\t{intensity}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _seed_result_artifacts(result: Result, source_output_dir: Path | None = None) -> None:
    if source_output_dir is not None and source_output_dir.is_dir():
        _reset_dir(result.output_dir)
        shutil.copytree(source_output_dir, result.output_dir, dirs_exist_ok=True)
        source_raw_name = None
        for candidate in (result.output_dir / "rawtools").glob("*_Ms_TIC_chromatogram.txt"):
            source_raw_name = candidate.name.removesuffix("_Ms_TIC_chromatogram.txt")
            break
        if source_raw_name:
            target_raw_name = result.raw_file.name
            for rawtools_file in (result.output_dir / "rawtools").glob(f"{source_raw_name}*"):
                renamed = rawtools_file.with_name(
                    rawtools_file.name.replace(source_raw_name, target_raw_name, 1)
                )
                rawtools_file.rename(renamed)
        source_qc = result.output_dir_rawtools_qc / "QcDataTable.csv"
        if source_qc.is_file():
            shutil.copy2(source_qc, result.raw_file.path.parent / "QcDataTable.csv")
        return

    maxquant_src = _seed_maxquant_output_dir()
    rawtools_src = _seed_rawtools_dir()

    _reset_dir(result.output_dir_maxquant)
    _reset_dir(result.output_dir_rawtools)
    _reset_dir(result.output_dir_rawtools_qc)

    for item in maxquant_src.iterdir():
        if item.is_file():
            shutil.copy2(item, result.output_dir_maxquant / item.name)

    metrics_src = rawtools_src / "SA001-R3-C-2ulF.raw_Metrics.txt"
    matrix_src = rawtools_src / "SA001-R3-C-2ulF.raw_Matrix.txt"
    qc_src = rawtools_src / "QcDataTable.csv"

    shutil.copy2(metrics_src, result.output_dir_rawtools / "rawtools_metrics.txt")
    shutil.copy2(matrix_src, result.output_dir_rawtools / "rawtools_matrix.txt")
    shutil.copy2(qc_src, result.output_dir_rawtools_qc / "QcDataTable.csv")
    shutil.copy2(qc_src, result.raw_file.path.parent / "QcDataTable.csv")

    raw_name = result.raw_file.name
    multiplier = max(1, result.raw_file.pk or 1)
    _write_demo_chromatogram(
        result.output_dir_rawtools / f"{raw_name}_Ms_TIC_chromatogram.txt",
        multiplier=multiplier,
    )
    _write_demo_chromatogram(
        result.output_dir_rawtools / f"{raw_name}_Ms2_TIC_chromatogram.txt",
        multiplier=multiplier + 3,
    )

    (result.output_dir_maxquant / "time.txt").write_text("00:06:42", encoding="utf-8")
    (result.output_dir_maxquant / "maxquant.out").write_text(
        "Finish writing tables\nDemo bootstrap run\n",
        encoding="utf-8",
    )
    (result.output_dir_maxquant / "maxquant.err").write_text("", encoding="utf-8")
    (result.output_dir_rawtools / "rawtools_metrics.err").write_text("", encoding="utf-8")
    (result.output_dir_rawtools_qc / "rawtools_qc.err").write_text("", encoding="utf-8")

    try:
        result.create_protein_quant()
    except Exception:
        # Demo bootstrap should remain usable even if parquet support is unavailable.
        pass


def _upsert_demo_raw_file(user: User, pipeline: Pipeline, filename: str) -> RawFile:
    for raw_file in RawFile.objects.filter(pipeline=pipeline, created_by=user):
        if raw_file.name == filename:
            if raw_file.use_downstream is not True:
                raw_file.use_downstream = True
                raw_file.save(update_fields=["use_downstream"])
            return raw_file

    raw_file = RawFile(
        pipeline=pipeline,
        created_by=user,
        orig_file=SimpleUploadedFile(filename, b"demo raw placeholder"),
        use_downstream=True,
    )
    raw_file._skip_auto_result = True
    raw_file.save()
    return raw_file


def bootstrap_demo_workspace(
    *,
    user_email: str,
    project_name: str = DEMO_PROJECT_NAME,
    pipeline_name: str = DEMO_PIPELINE_NAME,
    with_results: bool = False,
    force: bool = False,
    user_password: str | None = None,
) -> DemoBootstrapResult:
    user, created_user, generated_password = _upsert_user(
        user_email,
        password=user_password,
    )
    project, created_project = _upsert_project(user, project_name)
    pipeline, created_pipeline = _upsert_pipeline(user, project, pipeline_name)
    demo_seed_specs = _demo_seed_specs()
    demo_filenames = [spec["filename"] for spec in demo_seed_specs]

    raw_files: list[RawFile] = []
    results: list[Result] = []

    if force and with_results:
        _delete_demo_runs(pipeline, user, demo_filenames)
        _delete_demo_temp_run_dirs(demo_filenames)

    if with_results:
        for seed_spec in demo_seed_specs:
            filename = seed_spec["filename"]
            raw_file = _upsert_demo_raw_file(user, pipeline, filename)
            raw_files.append(raw_file)
            result, _ = Result.objects.get_or_create(
                raw_file=raw_file,
                defaults={"created_by": user, "input_source": "demo"},
            )
            update_fields = []
            if result.created_by_id != user.pk:
                result.created_by = user
                update_fields.append("created_by")
            if result.input_source != "demo":
                result.input_source = "demo"
                update_fields.append("input_source")
            if result.maxquant_task_id is not None:
                result.maxquant_task_id = None
                update_fields.append("maxquant_task_id")
            if result.rawtools_metrics_task_id is not None:
                result.rawtools_metrics_task_id = None
                update_fields.append("rawtools_metrics_task_id")
            if result.rawtools_qc_task_id is not None:
                result.rawtools_qc_task_id = None
                update_fields.append("rawtools_qc_task_id")
            if result.maxquant_task_submitted_at is not None:
                result.maxquant_task_submitted_at = None
                update_fields.append("maxquant_task_submitted_at")
            if result.rawtools_metrics_task_submitted_at is not None:
                result.rawtools_metrics_task_submitted_at = None
                update_fields.append("rawtools_metrics_task_submitted_at")
            if result.rawtools_qc_task_submitted_at is not None:
                result.rawtools_qc_task_submitted_at = None
                update_fields.append("rawtools_qc_task_submitted_at")
            if result.cancel_requested_at is not None:
                result.cancel_requested_at = None
                update_fields.append("cancel_requested_at")
            if update_fields:
                result.save(update_fields=update_fields)
            _seed_result_artifacts(
                result,
                source_output_dir=seed_spec["source_output_dir"],
            )
            results.append(result)

    return DemoBootstrapResult(
        user=user,
        project=project,
        pipeline=pipeline,
        raw_files=raw_files,
        results=results,
        created_user=created_user,
        created_project=created_project,
        created_pipeline=created_pipeline,
        generated_password=generated_password,
    )
