import os
import logging
import signal
import subprocess
import time
from celery import shared_task
from django.apps import apps

from omics.proteomics.maxquant import MaxquantRunner

from omics.proteomics.rawtools.quality_control import (
    rawtools_metrics_cmd,
    rawtools_qc_cmd,
)

PROCESS_TRACKING_FIELDS = {
    "maxquant": ("maxquant_pid", "maxquant_pgid"),
    "rawtools_metrics": ("rawtools_metrics_pid", "rawtools_metrics_pgid"),
    "rawtools_qc": ("rawtools_qc_pid", "rawtools_qc_pgid"),
}


def _safe_float(env_name, default):
    try:
        return float(os.getenv(env_name, default))
    except (TypeError, ValueError):
        return float(default)


def _safe_int(env_name, default):
    try:
        return int(os.getenv(env_name, default))
    except (TypeError, ValueError):
        return int(default)


def _available_memory_gb():
    # Linux containers expose MemAvailable in /proc/meminfo.
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    kb = float(line.split()[1])
                    return kb / 1024.0 / 1024.0
    except Exception:
        return None
    return None


def _normalized_load():
    try:
        load_1m = os.getloadavg()[0]
    except OSError:
        return None
    n_cpu = os.cpu_count() or 1
    return load_1m / float(n_cpu)


def _resources_available(min_free_mem_gb, max_load_per_cpu):
    available_gb = _available_memory_gb()
    norm_load = _normalized_load()

    mem_ok = True if available_gb is None else (available_gb >= min_free_mem_gb)
    load_ok = True if norm_load is None else (norm_load <= max_load_per_cpu)
    return mem_ok and load_ok, available_gb, norm_load


def _defer_if_busy(task, kind, min_free_mem_gb, max_load_per_cpu):
    ok, avail_gb, norm_load = _resources_available(
        min_free_mem_gb=min_free_mem_gb,
        max_load_per_cpu=max_load_per_cpu,
    )
    if ok:
        return

    retry_seconds = _safe_int("RESOURCE_RETRY_SECONDS", 60)
    logging.info(
        "[%s] Deferring for %ss (min_mem=%.1fGB, avail_mem=%sGB, max_load=%.2f, load=%s)",
        kind,
        retry_seconds,
        min_free_mem_gb,
        "?" if avail_gb is None else f"{avail_gb:.2f}",
        max_load_per_cpu,
        "?" if norm_load is None else f"{norm_load:.2f}",
    )
    raise task.retry(countdown=retry_seconds)


def _is_canceled_result(result_id):
    if not result_id:
        return False
    Result = apps.get_model("maxquant", "Result")
    return Result.objects.filter(pk=result_id, cancel_requested_at__isnull=False).exists()


def _terminate_process_group(proc, grace_seconds=5):
    if proc is None:
        return
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception as exc:
        logging.warning("Failed to SIGTERM process group for pid=%s: %s", pgid, exc)
        return

    def _pg_exists(group_id):
        try:
            os.killpg(group_id, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process group exists but is not signalable by this user.
            return True
        except Exception:
            return True

    deadline = time.monotonic() + max(0, grace_seconds)
    while time.monotonic() < deadline:
        if not _pg_exists(pgid):
            return
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception as exc:
        logging.warning("Failed to SIGKILL process group for pid=%s: %s", pgid, exc)


def _set_running_process(result_id, tracking_key, proc):
    if not result_id or not tracking_key or proc is None:
        return
    fields = PROCESS_TRACKING_FIELDS.get(tracking_key)
    if fields is None:
        return
    pid_field, pgid_field = fields
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pgid = None
    except OSError as exc:
        logging.warning(
            "[%s] Failed to resolve pgid for pid=%s: %s",
            tracking_key,
            proc.pid,
            exc,
        )
        pgid = None

    Result = apps.get_model("maxquant", "Result")
    Result.objects.filter(pk=result_id).update(
        **{
            pid_field: proc.pid,
            pgid_field: pgid,
        }
    )


def _clear_running_process(result_id, tracking_key, pid=None, pgid=None):
    if not result_id or not tracking_key:
        return
    fields = PROCESS_TRACKING_FIELDS.get(tracking_key)
    if fields is None:
        return
    pid_field, pgid_field = fields
    filters = {"pk": result_id}
    if pid is not None:
        filters[pid_field] = pid
    if pgid is not None:
        filters[pgid_field] = pgid
    Result = apps.get_model("maxquant", "Result")
    Result.objects.filter(**filters).update(
        **{
            pid_field: None,
            pgid_field: None,
        }
    )


def _reap_process(proc, timeout_seconds=2.0):
    if proc is None:
        return
    try:
        proc.wait(timeout=max(0.1, float(timeout_seconds)))
    except subprocess.TimeoutExpired:
        # Keep non-blocking behavior for worker threads; we'll try once more.
        try:
            proc.poll()
        except Exception:
            return
    except Exception:
        return


def _run_cancelable_shell_command(cmd, kind, result_id=None, tracking_key=None):
    poll_seconds = max(0.2, _safe_float("CANCEL_POLL_SECONDS", 2.0))
    kill_grace_seconds = _safe_int("CANCEL_KILL_GRACE_SECONDS", 5)
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            executable="/bin/bash",
            preexec_fn=os.setsid,
        )
    except Exception as exc:
        logging.exception("[%s] Failed to start command: %s", kind, exc)
        return 1

    pgid = None
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pass
    except OSError as exc:
        logging.warning("[%s] Failed to read process group for pid=%s: %s", kind, proc.pid, exc)

    _set_running_process(result_id, tracking_key, proc)
    logging.info("[%s] started pid=%s pgid=%s", kind, proc.pid, pgid)
    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                logging.info("[%s] finished pid=%s rc=%s", kind, proc.pid, rc)
                return rc

            if _is_canceled_result(result_id):
                logging.info(
                    "[%s] cancel requested during execution; terminating pid=%s pgid=%s",
                    kind,
                    proc.pid,
                    pgid,
                )
                _terminate_process_group(proc, grace_seconds=kill_grace_seconds)
                # Ensure the direct child process is reaped so canceled runs do not
                # leave zombie entries behind in long-lived celery workers.
                _reap_process(proc)
                return -1

            time.sleep(poll_seconds)
    finally:
        _clear_running_process(
            result_id=result_id,
            tracking_key=tracking_key,
            pid=proc.pid,
            pgid=pgid,
        )


@shared_task(bind=True, max_retries=None)
def rawtools_metrics(
    self, raw, output_dir, arguments=None, rerun=False, result_id=None
):
    if _is_canceled_result(result_id):
        logging.info("[rawtools_metrics] canceled before start (result_id=%s)", result_id)
        return
    _defer_if_busy(
        task=self,
        kind="rawtools_metrics",
        min_free_mem_gb=_safe_float("MIN_FREE_MEM_GB_RAWTOOLS", 2),
        max_load_per_cpu=_safe_float("MAX_LOAD_PER_CPU_RAWTOOLS", 0.95),
    )
    cmd = rawtools_metrics_cmd(
        raw=raw, output_dir=output_dir, rerun=rerun, arguments=arguments
    )
    if cmd is not None:
        if _is_canceled_result(result_id):
            logging.info(
                "[rawtools_metrics] canceled before execution (result_id=%s)",
                result_id,
            )
            return
        logging.info(f"[rawtools_metrics] {cmd}")
        print(f"[rawtools_metrics] {cmd}")
        _run_cancelable_shell_command(
            cmd,
            kind="rawtools_metrics",
            result_id=result_id,
            tracking_key="rawtools_metrics",
        )


@shared_task(bind=True, max_retries=None)
def rawtools_qc(self, input_dir, output_dir, rerun=False, result_id=None):
    if _is_canceled_result(result_id):
        logging.info("[rawtools_qc] canceled before start (result_id=%s)", result_id)
        return
    _defer_if_busy(
        task=self,
        kind="rawtools_qc",
        min_free_mem_gb=_safe_float("MIN_FREE_MEM_GB_RAWTOOLS", 2),
        max_load_per_cpu=_safe_float("MAX_LOAD_PER_CPU_RAWTOOLS", 0.95),
    )
    cmd = rawtools_qc_cmd(input_dir=input_dir, output_dir=output_dir, rerun=rerun)
    if cmd is not None:
        if _is_canceled_result(result_id):
            logging.info(
                "[rawtools_qc] canceled before execution (result_id=%s)", result_id
            )
            return
        logging.info(f"[rawtools_qc] {cmd}")
        print(f"[rawtools_qc] {cmd}")
        _run_cancelable_shell_command(
            cmd,
            kind="rawtools_qc",
            result_id=result_id,
            tracking_key="rawtools_qc",
        )


@shared_task(bind=True, max_retries=None)
def run_maxquant(self, raw_file, params, rerun=False, result_id=None):
    if _is_canceled_result(result_id):
        logging.info("[run_maxquant] canceled before start (result_id=%s)", result_id)
        return
    _defer_if_busy(
        task=self,
        kind="run_maxquant",
        min_free_mem_gb=_safe_float("MIN_FREE_MEM_GB_MAXQUANT", 8),
        max_load_per_cpu=_safe_float("MAX_LOAD_PER_CPU_MAXQUANT", 0.85),
    )
    if _is_canceled_result(result_id):
        logging.info(
            "[run_maxquant] canceled before execution (result_id=%s)", result_id
        )
        return
    mq = MaxquantRunner(verbose=True, **params)
    logging.info(f"[run_maxquant] raw_file={raw_file} params={params} rerun={rerun}")
    print(f"[run_maxquant] raw_file={raw_file} params={params} rerun={rerun}")
    # Prepare run dirs/files via MaxquantRunner, but execute through the
    # cancel-aware shell runner so cancel requests can stop active MaxQuant jobs.
    cmd = mq.run(raw_file, rerun=rerun, run=False)
    if cmd is None:
        return
    _run_cancelable_shell_command(
        cmd,
        kind="run_maxquant",
        result_id=result_id,
        tracking_key="maxquant",
    )
