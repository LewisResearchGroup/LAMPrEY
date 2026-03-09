import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def _assert(condition, message):
    if not condition:
        raise RuntimeError(message)


def _log(message):
    print(f"[runtime-smoke] {message}", flush=True)


def _read_text(path):
    target = Path(path)
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="ignore")


def main():
    smoke_tmpdir = tempfile.TemporaryDirectory(prefix="runtime-smoke-")
    smoke_tmp = Path(smoke_tmpdir.name)
    try:
        os.environ.setdefault("MPLCONFIGDIR", str(smoke_tmp / "matplotlib"))
        (smoke_tmp / "matplotlib").mkdir(parents=True, exist_ok=True)
        # PyCaret tries to create logs.log in the current working directory.
        # Use a writable temp workspace during the smoke probe.
        os.chdir(smoke_tmp)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

        import django

        django.setup()

        from maxquant.Result import Result
        from maxquant.defaults import ensure_bundled_maxquant_installed
        from maxquant.tasks import _run_cancelable_process
        from maxquant.rawtools import DEFAULT_RAWTOOLS_ARGS
        from main.asgi import application as asgi_application
        from main.wsgi import application as wsgi_application
        from omics.proteomics.rawtools.quality_control import (
            rawtools_metrics_spec,
            rawtools_qc_spec,
        )

        _log("starting runtime smoke check")
        _assert(asgi_application is not None, "ASGI application import failed.")
        _assert(wsgi_application is not None, "WSGI application import failed.")
        _log("ASGI/WSGI entrypoint import probe passed")
        bundled = ensure_bundled_maxquant_installed()
        _assert(bundled is not None and bundled.is_file(), "Bundled MaxQuant executable missing.")
        _log(f"bundled MaxQuant executable: {bundled}")

        fake_result = SimpleNamespace(
            raw_file=SimpleNamespace(
                pipeline=SimpleNamespace(
                    maxquant_executable="",
                )
            )
        )
        maxquant_cmd = Result.maxquantcmd.fget(fake_result)
        maxquant_parts = shlex.split(maxquant_cmd)
        _assert(maxquant_parts, "MaxQuant command resolution returned an empty command.")
        _assert(Path(maxquant_parts[-1]).is_file(), f"MaxQuant target missing: {maxquant_parts[-1]}")
        _log(f"resolved MaxQuant command: {maxquant_cmd}")

        rc = _run_cancelable_process(
            ["dotnet", "--list-runtimes"],
            kind="runtime_smoke_dotnet",
            cwd=str(smoke_tmp),
            stdout_path=str(smoke_tmp / "runtime_smoke_dotnet.out"),
            stderr_path=str(smoke_tmp / "runtime_smoke_dotnet.err"),
        )
        _assert(rc == 0, "dotnet --list-runtimes failed via task runner.")
        _log("dotnet runtime probe passed")
        rc = _run_cancelable_process(
            ["mono", "--version"],
            kind="runtime_smoke_mono",
            cwd=str(smoke_tmp),
            stdout_path=str(smoke_tmp / "runtime_smoke_mono.out"),
            stderr_path=str(smoke_tmp / "runtime_smoke_mono.err"),
        )
        _assert(rc == 0, "mono --version failed via task runner.")
        _log("mono runtime probe passed")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            raw_file = tmpdir_path / "sample.raw"
            raw_file.write_text("smoke", encoding="utf-8")
            metrics_dir = tmpdir_path / "rawtools_metrics"
            qc_dir = tmpdir_path / "rawtools_qc"

            metrics_spec = rawtools_metrics_spec(
                raw=raw_file,
                output_dir=metrics_dir,
                arguments=DEFAULT_RAWTOOLS_ARGS,
            )
            qc_spec = rawtools_qc_spec(
                input_dir=tmpdir_path,
                output_dir=qc_dir,
            )

            _assert(
                Path(metrics_spec["args"][0]).is_file() or shutil.which(metrics_spec["args"][0]),
                f"RawTools executable missing: {metrics_spec['args'][0]}",
            )
            _assert(
                Path(qc_spec["args"][0]).is_file() or shutil.which(qc_spec["args"][0]),
                f"RawTools executable missing: {qc_spec['args'][0]}",
            )
            _log(f"resolved RawTools executable: {metrics_spec['args'][0]}")
            stdout_path = tmpdir_path / "runtime_smoke_rawtools.out"
            stderr_path = tmpdir_path / "runtime_smoke_rawtools.err"
            rc = _run_cancelable_process(
                [metrics_spec["args"][0], "--help"],
                kind="runtime_smoke_rawtools",
                cwd=tmpdir,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
            )
            rawtools_output = f"{_read_text(stdout_path)}\n{_read_text(stderr_path)}".lower()
            rawtools_help_seen = any(
                marker in rawtools_output
                for marker in ("rawtools", "usage", "options", "parse", "qc")
            )
            _assert(
                rc == 0 or rawtools_help_seen,
                "rawtools.sh help probe did not produce recognizable output via task runner.",
            )
            _log("RawTools probe passed")

        _log("runtime smoke check passed")
    finally:
        smoke_tmpdir.cleanup()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
