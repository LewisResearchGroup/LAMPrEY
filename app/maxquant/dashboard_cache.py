import json
import logging
from pathlib import Path as P
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from django.apps import apps


def sort_dashboard_qc_scope(frame):
    if frame is None or frame.empty:
        return frame

    df = frame.copy()
    sort_columns = []
    ascending = []

    if "DateAcquired" in df.columns:
        df["DateAcquired"] = pd.to_datetime(df["DateAcquired"], errors="coerce")
        sort_columns.append("DateAcquired")
        ascending.append(True)

    if "RawFile" in df.columns:
        raw_series = df["RawFile"].fillna("").astype(str)
        df["_rawfile_sort"] = raw_series.str.lower()
        sort_columns.append("_rawfile_sort")
        ascending.append(True)

    if "RunKey" in df.columns:
        df["_runkey_sort"] = df["RunKey"].fillna("").astype(str)
        sort_columns.append("_runkey_sort")
        ascending.append(True)

    if sort_columns:
        df = df.sort_values(sort_columns, ascending=ascending, na_position="last").reset_index(drop=True)

    if "Index" in df.columns:
        df["Index"] = np.arange(1, len(df) + 1, dtype=int)

    return df.drop(columns=["_rawfile_sort", "_runkey_sort"], errors="ignore")


def pipeline_dashboard_qc_cache_path(pipeline):
    return pipeline.path / "dashboard_qc_scope_cache.json"


def write_pipeline_dashboard_qc_cache(cache_path, df):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(json.loads(df.to_json(orient="records", date_format="iso")))
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(cache_path.parent), delete=False) as handle:
        handle.write(payload)
        temp_name = handle.name
    P(temp_name).replace(cache_path)


def read_pipeline_dashboard_qc_cache(cache_path):
    if not cache_path.is_file():
        return pd.DataFrame()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    df = pd.DataFrame(payload)
    if "DateAcquired" in df.columns:
        df["DateAcquired"] = pd.to_datetime(df["DateAcquired"], errors="coerce")
    return df


def build_pipeline_dashboard_qc_cache(pipeline, results):
    frames = []
    for result in results:
        df = result.dashboard_qc_data()
        if df is None or df.empty:
            continue
        df = df.copy()
        df["RunKey"] = f"rf{result.raw_file_id}"
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return sort_dashboard_qc_scope(combined)


def pipeline_dashboard_qc_cache_is_stale(pipeline, results):
    cache_path = pipeline_dashboard_qc_cache_path(pipeline)
    if not cache_path.is_file():
        return True

    cache_mtime = cache_path.stat().st_mtime
    cached_rows = read_pipeline_dashboard_qc_cache(cache_path)
    if len(cached_rows.index) != len(results):
        return True

    for result in results:
        if result.dashboard_qc_cache_is_stale():
            return True
        run_cache = result.dashboard_qc_cache_path
        if not run_cache.is_file():
            return True
        if run_cache.stat().st_mtime > cache_mtime:
            return True
    return False


def pipeline_dashboard_qc_data(pipeline, force_update=False):
    Result = apps.get_model("maxquant", "Result")
    results = list(
        Result.objects.filter(raw_file__pipeline=pipeline)
        .select_related("raw_file__created_by")
        .order_by("raw_file__created", "raw_file_id")
    )
    cache_path = pipeline_dashboard_qc_cache_path(pipeline)
    if force_update or pipeline_dashboard_qc_cache_is_stale(pipeline, results):
        df = build_pipeline_dashboard_qc_cache(pipeline, results)
        write_pipeline_dashboard_qc_cache(cache_path, df)
        return df
    return read_pipeline_dashboard_qc_cache(cache_path)


def warm_dashboard_caches_for_result(result):
    if result is None:
        return
    try:
        result.dashboard_qc_data(force_update=True)
        pipeline_dashboard_qc_data(result.pipeline, force_update=True)
        logging.warning(
            "[perf] Dashboard QC caches warmed result=%s pipeline=%s",
            result.pk,
            result.pipeline.slug,
        )
    except Exception as exc:
        logging.warning(
            "Dashboard QC cache warm failed for result=%s pipeline=%s: %s",
            getattr(result, "pk", None),
            getattr(getattr(result, "pipeline", None), "slug", None),
            exc,
        )
