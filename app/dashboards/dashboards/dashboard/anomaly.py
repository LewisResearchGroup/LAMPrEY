import os
import re
import io
import json
import hashlib
import zipfile
import pandas as pd

import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from omics.proteomics import ProteomicsQC

from dashboards.dashboards.dashboard import config as C
from dashboards.dashboards.dashboard import tools as T


layout = html.Div(
    style={"display": "flex", "flexDirection": "row", "height": "100%", "minHeight": "400px", "gap": "12px"},
    children=[
        # ── Left: heatmap plot area ──
        html.Div(
            className="pqc-anomaly-plot-area",
            style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
            children=[
                html.Div(
                    "No anomaly plot data available for this scope.",
                    id="anomaly-empty-state",
                    className="pqc-empty-state",
                    style={"display": "none"},
                ),
                html.Div(
                    className="pqc-anomaly-loading-scope",
                    style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                    children=[
                        html.Div(id="anomaly-progress-probe", className="pqc-hidden-trigger"),
                        dcc.Graph(
                            id="anomaly-figure",
                            figure={},
                            responsive=True,
                            style={
                                "display": "block",
                                "width": "100%",
                                "height": "100%",
                                "flex": "1 1 auto",
                                "minHeight": "0",
                            },
                        ),
                    ],
                ),
            ],
        ),
        # ── Right: settings sidebar ──
        html.Div(
            className="pqc-anomaly-sidebar",
            children=[
                html.Div(
                    className="pqc-anomaly-head",
                    children=[
                        html.Div("Anomaly Settings", className="pqc-panel-kicker"),
                    ],
                ),
                html.Div(
                    className="pqc-anomaly-control-block",
                    children=[
                        html.Div("Outlier fraction", className="pqc-field-label"),
                        html.Div(
                            className="pqc-anomaly-slider-wrap",
                            children=[
                                dcc.Slider(
                                    id="anomaly-fraction",
                                    value=5,
                                    min=1,
                                    max=100,
                                    step=1,
                                    marks={
                                        1: {"label": "1%"},
                                        50: {"label": "50%"},
                                        100: {"label": "100%"},
                                    },
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-anomaly-control-block",
                    children=[
                        html.Div("Row order", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="anomaly-row-order",
                            className="pqc-anomaly-dropdown",
                            clearable=False,
                            searchable=False,
                            options=[
                                {"label": "Input order", "value": "input"},
                                {"label": "Anomalous first", "value": "anomalous_first"},
                            ],
                            value="input",
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-anomaly-control-block",
                    children=[
                        html.Div("Metrics shown", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="anomaly-metric-count",
                            className="pqc-anomaly-dropdown",
                            clearable=False,
                            searchable=False,
                            options=[
                                {"label": "10", "value": 10},
                                {"label": "15", "value": 15},
                                {"label": "20", "value": 20},
                                {"label": "25", "value": 25},
                                {"label": "30", "value": 30},
                                {"label": "All", "value": "all"},
                            ],
                            value=20,
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-anomaly-control-block",
                    children=[
                        html.Div("Export", className="pqc-field-label"),
                        html.Button(
                            "Download data",
                            id="anomaly-download-btn",
                            className="pqc-anomaly-apply-btn",
                            n_clicks=0,
                        ),
                        dcc.Download(id="anomaly-download"),
                    ],
                ),
                html.Div(
                    className="pqc-anomaly-apply-panel",
                    children=[
                        html.Div("Apply changes", className="pqc-field-label"),
                        html.Button(
                            "Apply flag changes",
                            id="anomaly-apply",
                            className="pqc-anomaly-apply-btn",
                            n_clicks=0,
                            disabled=True,
                        ),
                        html.Div(
                            id="anomaly-apply-status",
                            className="pqc-anomaly-apply-status",
                        ),
                    ],
                ),
                html.Div("5%", id="anomaly-fraction-value", className="pqc-hidden-trigger"),
                html.Div(
                    className="pqc-anomaly-preview-panel",
                    children=[
                        html.Div(
                            "Preview only. Review proposed flag changes before applying them.",
                            id="anomaly-preview-summary",
                            className="pqc-anomaly-subtitle",
                        ),
                        html.Div(
                            id="anomaly-preview-details",
                            className="pqc-anomaly-subtitle",
                        ),
                    ],
                ),
            ],
        ),
    ]
)


def _top_anomaly_contributors(run_key, shap_values, max_items=3):
    if shap_values is None or shap_values.empty:
        return []
    run_key = str(run_key)
    shap_frame = shap_values.copy()
    shap_frame.index = shap_frame.index.astype(str)
    if run_key not in shap_frame.index:
        return []

    series = pd.to_numeric(shap_frame.loc[run_key], errors="coerce").dropna()
    if series.empty:
        return []

    negative = series[series < 0].sort_values()
    ranked = negative if not negative.empty else series.sort_values()
    contributors = []
    for metric, value in ranked.head(max_items).items():
        contributors.append(
            {
                "metric": str(metric),
                "shap_value": float(value),
            }
        )
    return contributors


def compute_flag_proposals(qc_data, predictions, shap_values=None):
    if qc_data is None or qc_data.empty or predictions is None or predictions.empty:
        return {
            "run_keys_to_flag": [],
            "run_keys_to_unflag": [],
            "preview_rows": [],
        }

    frame = qc_data.copy()
    if "Flagged" not in frame.columns:
        frame["Flagged"] = False
    frame["Flagged"] = frame["Flagged"].fillna(False).astype(bool)

    index_col = "RunKey" if "RunKey" in frame.columns else "RawFile"
    label_col = "SampleLabel" if "SampleLabel" in frame.columns else "RawFile"
    frame[index_col] = frame[index_col].astype(str)
    frame[label_col] = frame[label_col].astype(str)

    prediction_index = predictions.index.astype(str)
    anomaly_mask = predictions["Anomaly"].astype(int) == 1
    normal_mask = predictions["Anomaly"].astype(int) == 0

    currently_unflagged = set(frame.loc[~frame["Flagged"], index_col].astype(str))
    currently_flagged = set(frame.loc[frame["Flagged"], index_col].astype(str))

    run_keys_to_flag = [
        key for key in prediction_index[anomaly_mask].tolist() if key in currently_unflagged
    ]
    run_keys_to_unflag = [
        key for key in prediction_index[normal_mask].tolist() if key in currently_flagged
    ]

    preview_rows = []
    for action, keys in (("flag", run_keys_to_flag), ("unflag", run_keys_to_unflag)):
        for key in keys:
            row = frame.loc[frame[index_col] == key].iloc[0]
            preview_row = {
                "run_key": key,
                "sample_label": row[label_col],
                "raw_file": row.get("RawFile", row[label_col]),
                "action": action,
                "current_flagged": bool(row["Flagged"]),
            }
            if shap_values is not None and action == "flag":
                preview_row["top_contributors"] = _top_anomaly_contributors(
                    key, shap_values
                )
            preview_rows.append(preview_row)

    return {
        "run_keys_to_flag": run_keys_to_flag,
        "run_keys_to_unflag": run_keys_to_unflag,
        "preview_rows": preview_rows,
    }


def _available_anomaly_columns(df):
    if df is None or df.empty:
        return []

    available = [
        column
        for column in C.qc_columns_options
        if column in df.columns and column not in C.qc_columns_always
    ]

    tmt_pattern = re.compile(r"^TMT\d+_(missing_values|peptide_count|protein_group_count)$")
    detected_tmt = sorted(
        [column for column in df.columns if tmt_pattern.match(str(column))],
        key=lambda column: (
            int(re.search(r"\d+", str(column)).group(0)),
            str(column),
        ),
    )
    for column in detected_tmt:
        if column not in available:
            available.append(column)
    return available


def apply_anomaly_flag_changes(proposal, project, pipeline, user, n_clicks):
    if not n_clicks:
        raise PreventUpdate
    if not proposal:
        return "No anomaly flag changes to apply.", dash.no_update
    if project != proposal.get("project") or pipeline != proposal.get("pipeline"):
        return "Scope changed. Recompute anomaly preview before applying.", dash.no_update
    if user is None:
        return "Missing user context.", dash.no_update

    run_keys_to_flag = list(proposal.get("run_keys_to_flag") or [])
    run_keys_to_unflag = list(proposal.get("run_keys_to_unflag") or [])

    if run_keys_to_flag:
        response = T.set_rawfile_action(project, pipeline, run_keys_to_flag, "flag", user=user)
        if response.get("status") != "success":
            return response.get("status", "Could not apply anomaly flags."), dash.no_update
    if run_keys_to_unflag:
        response = T.set_rawfile_action(project, pipeline, run_keys_to_unflag, "unflag", user=user)
        if response.get("status") != "success":
            return response.get("status", "Could not apply anomaly flags."), dash.no_update

    total = len(run_keys_to_flag) + len(run_keys_to_unflag)
    return (
        f"Applied {total} anomaly flag change(s). The QC scope has been refreshed.",
        json.dumps({"applied": n_clicks, "project": project, "pipeline": pipeline}),
    )


def callbacks(app):
    min_samples_for_anomaly = 3

    def _short_label(value, max_len=26):
        text = str(value)
        if len(text) <= max_len:
            return text
        return f"{text[:max_len-1]}…"

    def _short_label_keep_ends(value, max_len=30, tail_len=8):
        text = str(value)
        if len(text) <= max_len:
            return text
        head_len = max(8, max_len - tail_len - 1)
        return f"{text[:head_len]}…{text[-tail_len:]}"

    def _pretty_metric_name(name):
        text = str(name)
        text = text.replace("_", " ")
        text = text.replace(" [ppm] (ave)", " delta m/z (ppm)")
        text = text.replace("[%]", "(%)")
        text = text.replace("calibrated retention time qc1", "calibrated retention time qc1")
        text = text.replace("Uncalibrated - Calibrated m/z", "delta m/z")
        return text

    @app.callback(
        Output("anomaly-fraction-value", "children"),
        Input("anomaly-fraction", "value"),
    )
    def render_fraction_value(value):
        return f"{int(value or 0)}%"

    @app.callback(
        Output("shapley-values", "children"),
        Output("anomaly-progress-probe", "children"),
        Output("anomaly-cache-key", "children"),
        Output("anomaly-proposed-flags", "data"),
        Input("tabs", "value"),
        Input("project", "value"),
        Input("pipeline", "value"),
        Input("anomaly-fraction", "value"),
        Input("qc-scope-data", "data"),
        State("anomaly-cache-key", "children"),
        State("shapley-values", "children"),
    )
    def run_anomaly_detection(
        tab,
        project,
        pipeline,
        fraction_in,
        scope_data,
        cached_key,
        cached_payload,
        **kwargs,
    ):
        if tab != "anomaly":
            raise PreventUpdate
        if project is None or pipeline is None:
            raise PreventUpdate
        if not scope_data:
            raise PreventUpdate

        fraction = (fraction_in or 5) / 100.0
        algorithm = "iforest"
        # Cache against the current scope payload itself, not just the selected
        # project/pipeline parameters, so a changed sample set forces recompute.
        scope_sig = hashlib.md5(json.dumps(scope_data, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        qc_data = pd.DataFrame(T.dashboard_rows(scope_data))
        model_columns = _available_anomaly_columns(qc_data)
        cache_key = json.dumps(
            {
                "project": project,
                "pipeline": pipeline,
                "fraction": int(fraction_in or 5),
                "columns": sorted(model_columns),
                "scope_sig": scope_sig,
                "algorithm": algorithm,
            },
            sort_keys=True,
        )
        if cached_key == cache_key and cached_payload:
            raise PreventUpdate

        user = kwargs.get("user")
        uid = getattr(user, "uuid", None)
        if uid is None:
            raise PreventUpdate

        # Use already loaded QC scope data from dashboard state to avoid
        # secondary API calls that may fail auth-context checks.
        if qc_data.empty or "RawFile" not in qc_data.columns:
            return None, f"empty-{project}-{pipeline}-{fraction_in}", cache_key, None
        sample_count = len(qc_data.index)
        if sample_count < min_samples_for_anomaly:
            return None, f"insufficient-{project}-{pipeline}-{sample_count}", cache_key, None
        index_col = "RunKey" if "RunKey" in qc_data.columns else "RawFile"
        qc_model = qc_data.set_index(index_col)

        # Replace column fully None → True
        if "Use Downstream" not in qc_data.columns:
            qc_data["Use Downstream"] = True
        if qc_data["Use Downstream"].isna().all():
            qc_data["Use Downstream"] = True
        if "Flagged" not in qc_data.columns:
            qc_data["Flagged"] = False

        params = dict(n_estimators=1000, max_features=10)

        try:
            predictions, df_shap = T.detect_anomalies(
                qc_model,
                algorithm=algorithm,
                columns=model_columns,
                fraction=fraction,
                **params,
            )
        except Exception as exc:
            logging.warning(f"Anomaly detection skipped for {project}/{pipeline}: {exc}")
            return None, f"empty-{project}-{pipeline}-{fraction_in}", cache_key, None

        proposal = compute_flag_proposals(qc_data, predictions, df_shap)
        proposal.update(
            {
                "project": project,
                "pipeline": pipeline,
                "fraction": int(fraction_in or 5),
                "scope_sig": scope_sig,
                "cache_key": cache_key,
            }
        )

        payload = (
            df_shap.to_json(orient="split")
            if df_shap is not None
            else None
        )
        return payload, f"updated-{project}-{pipeline}-{fraction_in}", cache_key, proposal


    @app.callback(
        Output("anomaly-figure", "figure"),
        Output("anomaly-figure", "config"),
        Output("anomaly-figure", "style"),
        Output("anomaly-empty-state", "children"),
        Output("anomaly-empty-state", "style"),
        Input("shapley-values", "children"),
        Input("qc-scope-data", "data"),
        Input("tabs", "value"),
        Input("anomaly-row-order", "value"),
        Input("anomaly-metric-count", "value"),
    )
    def plot_shapley(shapley_values, qc_data, tab, row_order, metric_count):
        config = T.gen_figure_config(
            filename="Anomaly-Detection-Shapley-values",
            editable=False,
        )
        config["displayModeBar"] = False
        hidden_graph_style = {
            "display": "none",
            "width": "100%",
            "height": "100%",
            "margin": "0",
        }
        visible_graph_style = {
            "display": "block",
            "width": "100%",
            "height": "100%",
            "margin": "0",
        }
        default_empty_message = "No anomaly plot data available for this scope."

        if tab != "anomaly":
            return {}, config, hidden_graph_style, default_empty_message, {"display": "none"}

        qc_data = pd.DataFrame(T.dashboard_rows(qc_data))
        if qc_data.empty:
            return {}, config, hidden_graph_style, default_empty_message, {"display": "flex"}
        if "RawFile" not in qc_data.columns:
            return {}, config, hidden_graph_style, default_empty_message, {"display": "flex"}
        sample_count = len(qc_data.index)
        if sample_count < min_samples_for_anomaly:
            return (
                {},
                config,
                hidden_graph_style,
                f"Anomaly detection requires at least {min_samples_for_anomaly} samples. Current selection has {sample_count}.",
                {"display": "flex"},
            )
        if shapley_values is None:
            return {}, config, hidden_graph_style, default_empty_message, {"display": "flex"}

        try:
            df_shap = pd.read_json(shapley_values, orient="split")
        except ValueError:
            # Backward compatibility with cached payloads serialized
            # using pandas default orient.
            df_shap = pd.read_json(shapley_values)

        # samples on rows, QC metrics on columns
        row_keys = (
            qc_data["RunKey"].astype(str)
            if "RunKey" in qc_data.columns
            else qc_data["RawFile"].astype(str)
        )
        row_labels = (
            qc_data["SampleLabel"].astype(str)
            if "SampleLabel" in qc_data.columns
            else qc_data["RawFile"].astype(str)
        )
        label_by_key = dict(zip(row_keys, row_labels))
        df_shap.index = df_shap.index.astype(str)
        df_shap = df_shap.reindex(row_keys).fillna(0)
        df_shap.index = [label_by_key.get(key, key) for key in row_keys]

        if row_order == "anomalous_first":
            sample_rank = df_shap.abs().mean(axis=1).sort_values(ascending=False).index
            df_shap = df_shap.reindex(sample_rank)

        if metric_count != "all":
            max_metrics = int(metric_count or 20)
            metric_rank = df_shap.abs().mean(axis=0).sort_values(ascending=False).index
            df_shap = df_shap.loc[:, metric_rank[:max_metrics]]

        df_plot = df_shap.copy()
        df_plot.index = [_short_label_keep_ends(v, max_len=30, tail_len=8) for v in df_plot.index]
        df_plot.columns = [_short_label(_pretty_metric_name(c), max_len=30) for c in df_plot.columns]

        # Display metrics on y-axis and samples on x-axis.
        fig = T.px_heatmap(
            df_plot.T,
            layout_kws=dict(),
        )

        # Clean axes
        fig.update_xaxes(showgrid=False, zeroline=False)
        fig.update_yaxes(showgrid=False, zeroline=False,
                         side="left", ticklabelposition="outside")

        # Size & spacing
        fig.update_layout(
            width=None,
            margin=dict(l=14, r=20, t=6, b=24),
            coloraxis_colorbar=dict(
                x=1.02,
                y=0.48,
                yanchor="middle",
                thickness=14,
                len=0.76,
            ),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
        )

        # X label rotation
        fig.update_xaxes(
            tickangle=0,
            ticklabelposition="outside",
            automargin=True,
            title_text="Samples",
            title_standoff=12,
            showticklabels=False,
            ticks="",
        )
        fig.update_yaxes(
            title_text="QC metrics",
            title_standoff=20,
            automargin=True,
        )

        # SHAP diverging scale
        heatmap = [t for t in fig.data if t.type == "heatmap"][0]
        zmin = float(df_plot.values.min())
        zmax = float(df_plot.values.max())
        rng  = max(abs(zmin), abs(zmax))

        heatmap.zmin = -rng
        heatmap.zmax =  rng
        heatmap.zmid = 0
        # IsolationForest SHAP explains a normality-oriented model output:
        # negative values push toward anomaly, positive values toward normality.
        # Use the non-reversed scale so anomalous values render as red warnings.
        heatmap.colorscale = "RdBu"

        heatmap.colorbar.title = dict(
            text="SHAP (- anomalous | + normal)",
            side="right",
        )
        heatmap.colorbar.tickvals = [-rng, 0, rng]
        heatmap.colorbar.ticktext = ["More anomalous", "0", "More normal"]
        heatmap.colorbar.tickfont = dict(size=9)
        heatmap.colorbar.title.font = dict(size=11)

        base_font = dict(C.figure_font) if isinstance(C.figure_font, dict) else {}
        fig.update_layout(font={**base_font, "size": 11})
        fig.update_xaxes(title_font=dict(size=12))
        fig.update_yaxes(title_font=dict(size=12), tickfont=dict(size=9))

        return fig, config, visible_graph_style, default_empty_message, {"display": "none"}

    @app.callback(
        Output("anomaly-preview-summary", "children"),
        Output("anomaly-preview-details", "children"),
        Output("anomaly-apply", "disabled"),
        Input("anomaly-proposed-flags", "data"),
        Input("tabs", "value"),
    )
    def render_proposed_flag_changes(proposal, tab):
        if tab != "anomaly":
            raise PreventUpdate

        if not proposal:
            return (
                "Preview only. No anomaly flag changes are currently proposed.",
                "",
                True,
            )

        preview_rows = list(proposal.get("preview_rows") or [])
        n_flag = len(proposal.get("run_keys_to_flag") or [])
        n_unflag = len(proposal.get("run_keys_to_unflag") or [])
        total = len(preview_rows)
        if total == 0:
            return (
                "Preview only. The current anomaly model does not suggest any flag changes.",
                "Manual flags are unchanged until you explicitly apply a proposal.",
                True,
            )

        preview_lines = []
        for row in preview_rows[:6]:
            action_label = "Flag" if row.get("action") == "flag" else "Unflag"
            preview_lines.append(
                html.Div(f"{action_label}: {row.get('sample_label', row.get('run_key', 'sample'))}")
            )
        if total > 6:
            preview_lines.append(html.Div(f"...and {total - 6} more proposed change(s)."))

        summary = (
            f"Preview only: {n_flag} sample(s) would be flagged and "
            f"{n_unflag} sample(s) would be unflagged."
        )
        details = html.Div(
            [
                html.Div(preview_lines),
            ]
        )
        return summary, details, False

    @app.callback(
        Output("anomaly-apply-status", "children"),
        Output("anomaly-apply-refresh", "data"),
        Input("anomaly-apply", "n_clicks"),
        State("anomaly-proposed-flags", "data"),
        State("project", "value"),
        State("pipeline", "value"),
    )
    def apply_proposed_flag_changes(n_clicks, proposal, project, pipeline, **kwargs):
        user = kwargs.get("user")
        return apply_anomaly_flag_changes(
            proposal=proposal,
            project=project,
            pipeline=pipeline,
            user=user,
            n_clicks=n_clicks,
        )

    @app.callback(
        Output("anomaly-download", "data"),
        Input("anomaly-download-btn", "n_clicks"),
        State("shapley-values", "children"),
        State("qc-scope-data", "data"),
        State("anomaly-row-order", "value"),
        State("anomaly-metric-count", "value"),
        State("anomaly-proposed-flags", "data"),
        State("project", "value"),
        State("pipeline", "value"),
    )
    def download_anomaly_data(
        n_clicks,
        shapley_values,
        scope_data,
        row_order,
        metric_count,
        proposal,
        project,
        pipeline,
    ):
        if not n_clicks:
            raise PreventUpdate
        if shapley_values is None or not scope_data:
            raise PreventUpdate

        qc_data = pd.DataFrame(T.dashboard_rows(scope_data))
        if qc_data.empty or "RawFile" not in qc_data.columns:
            raise PreventUpdate

        try:
            df_shap = pd.read_json(shapley_values, orient="split")
        except ValueError:
            df_shap = pd.read_json(shapley_values)

        # Build labeled index (same logic as the plot callback)
        row_keys = (
            qc_data["RunKey"].astype(str)
            if "RunKey" in qc_data.columns
            else qc_data["RawFile"].astype(str)
        )
        row_labels = (
            qc_data["SampleLabel"].astype(str)
            if "SampleLabel" in qc_data.columns
            else qc_data["RawFile"].astype(str)
        )
        label_by_key = dict(zip(row_keys, row_labels))
        df_shap.index = df_shap.index.astype(str)
        df_shap = df_shap.reindex(row_keys).fillna(0)

        # Add anomaly label column from proposal
        anomaly_keys = set()
        if proposal:
            anomaly_keys = set(proposal.get("run_keys_to_flag") or [])
        df_shap["__anomaly_label__"] = [
            "Anomaly" if key in anomaly_keys else "Normal"
            for key in row_keys
        ]

        df_shap.index = [label_by_key.get(key, key) for key in row_keys]

        if row_order == "anomalous_first":
            sample_rank = df_shap.drop(columns=["__anomaly_label__"]).abs().mean(axis=1).sort_values(ascending=False).index
            df_shap = df_shap.reindex(sample_rank)

        if metric_count != "all":
            max_metrics = int(metric_count or 20)
            shap_cols = [c for c in df_shap.columns if c != "__anomaly_label__"]
            metric_rank = df_shap[shap_cols].abs().mean(axis=0).sort_values(ascending=False).index
            keep = list(metric_rank[:max_metrics])
            if "__anomaly_label__" not in keep:
                keep.append("__anomaly_label__")
            df_shap = df_shap.loc[:, keep]

        # Extract anomaly labels, then drop the helper column
        anomaly_labels = df_shap.pop("__anomaly_label__")

        # Use full metric names (not truncated) for the CSV
        df_shap.columns = [_pretty_metric_name(c) for c in df_shap.columns]

        # Prepend the anomaly label
        df_out = df_shap.copy()
        df_out.insert(0, "Anomaly Label", anomaly_labels.values)
        df_out.index.name = "Sample"

        base = f"anomaly-{project or 'project'}-{pipeline or 'pipeline'}"

        # Build ZIP with CSV + heatmap PNG
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            csv_buf = io.StringIO()
            df_out.to_csv(csv_buf)
            zf.writestr(f"{base}-shap-values.csv", csv_buf.getvalue())

            # Render heatmap with matplotlib/seaborn
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import seaborn as sns

                # Build the plot-ready matrix (same labels as the Plotly heatmap)
                df_plot = df_shap.copy()
                df_plot.index = [
                    _short_label_keep_ends(v, max_len=30, tail_len=8)
                    for v in df_plot.index
                ]
                df_plot.columns = [
                    _short_label(c, max_len=30) for c in df_plot.columns
                ]

                n_metrics = len(df_plot.columns)
                n_samples = len(df_plot.index)
                fig_w = max(6, 1.0 * n_samples + 3)
                fig_h = max(4, 0.35 * n_metrics + 1.5)

                rng = max(abs(df_plot.values.min()), abs(df_plot.values.max()))
                fig_mpl, ax = plt.subplots(figsize=(fig_w, fig_h))
                sns.heatmap(
                    df_plot.T,
                    ax=ax,
                    cmap="RdBu",
                    center=0,
                    vmin=-rng,
                    vmax=rng,
                    linewidths=0.5,
                    linecolor="#ffffff",
                    cbar_kws={
                        "label": "SHAP (- anomalous | + normal)",
                        "shrink": 0.8,
                    },
                )
                ax.set_xlabel("Samples", fontsize=11)
                ax.set_ylabel("QC Metrics", fontsize=11)
                ax.tick_params(axis="y", labelsize=8)
                ax.tick_params(axis="x", labelsize=8, rotation=45)
                plt.tight_layout()

                png_buf = io.BytesIO()
                fig_mpl.savefig(png_buf, format="png", dpi=150)
                plt.close(fig_mpl)
                png_buf.seek(0)
                zf.writestr(f"{base}-heatmap.png", png_buf.getvalue())
            except Exception:
                pass  # matplotlib/seaborn not available — skip figure

        return dcc.send_bytes(zip_buf.getvalue(), f"{base}.zip")
