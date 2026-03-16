import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from dashboards.dashboards.dashboard import config as C
from dashboards.dashboards.dashboard import tools as T


X_AXIS_LABELS = {
    "Index": "Sample Index",
    "RawFile": "Sample",
    "DateAcquired": "Acquisition Date",
}
X_AXIS_OPTIONS = [{"label": v, "value": k} for k, v in X_AXIS_LABELS.items()]

GRAPH_STYLE = {
    "width": "100%",
    "height": "100%",
    "flex": "1 1 auto",
    "minHeight": "0",
}


def _thin_ticks(tick_vals, tick_text, max_labels=15):
    """Reduce tick density so labels are readable at any sample count.

    Shows at most *max_labels* evenly-spaced labels, always keeping
    the first and last tick visible.
    """
    n = len(tick_vals)
    if n <= max_labels:
        return tick_vals, tick_text
    step = max(1, n // max_labels)
    keep = set(range(0, n, step))
    keep.add(n - 1)
    return (
        [v for i, v in enumerate(tick_vals) if i in keep],
        [t for i, t in enumerate(tick_text) if i in keep],
    )

PROTEIN_METRICS = {
    "Reporter intensity corrected": {
        "label": "Reporter intensity",
        "y_title": "Log2 Intensity",
        "empty_message": "No reporter intensity columns are available for these proteins.",
        "filename": "PQC-protein-explorer-intensity",
    },
    "Score": {
        "label": "Andromeda score",
        "y_title": "Andromeda Score",
        "empty_message": "No Andromeda score values are available for these proteins.",
        "filename": "PQC-protein-explorer-score",
    },
    "MS/MS count": {
        "label": "MS/MS count",
        "y_title": "MS/MS Count",
        "empty_message": "No MS/MS count values are available for these proteins.",
        "filename": "PQC-protein-explorer-msms-count",
    },
    "Peptides": {
        "label": "Peptides",
        "y_title": "Peptides",
        "empty_message": "No peptide-count values are available for these proteins.",
        "filename": "PQC-protein-explorer-peptides",
    },
    "Razor + unique peptides": {
        "label": "Razor + unique peptides",
        "y_title": "Razor + Unique Peptides",
        "empty_message": "No razor+unique peptide values are available for these proteins.",
        "filename": "PQC-protein-explorer-razor-unique-peptides",
    },
    "Unique peptides": {
        "label": "Unique peptides",
        "y_title": "Unique Peptides",
        "empty_message": "No unique peptide values are available for these proteins.",
        "filename": "PQC-protein-explorer-unique-peptides",
    },
    "Sequence coverage [%]": {
        "label": "Sequence coverage (%)",
        "y_title": "Sequence Coverage (%)",
        "empty_message": "No sequence coverage values are available for these proteins.",
        "filename": "PQC-protein-explorer-sequence-coverage",
    },
    "Unique + razor sequence coverage [%]": {
        "label": "Unique + razor coverage (%)",
        "y_title": "Unique + Razor Coverage (%)",
        "empty_message": "No unique+razor sequence coverage values are available for these proteins.",
        "filename": "PQC-protein-explorer-unique-razor-coverage",
    },
    "Unique sequence coverage [%]": {
        "label": "Unique sequence coverage (%)",
        "y_title": "Unique Sequence Coverage (%)",
        "empty_message": "No unique sequence coverage values are available for these proteins.",
        "filename": "PQC-protein-explorer-unique-coverage",
    },
    "Q-value": {
        "label": "Q-value",
        "y_title": "Q-value",
        "empty_message": "No Q-value values are available for these proteins.",
        "filename": "PQC-protein-explorer-q-value",
    },
}
PROTEIN_METRIC_OPTIONS = [
    {"label": spec["label"], "value": key}
    for key, spec in PROTEIN_METRICS.items()
]


layout = html.Div(
    style={"display": "flex", "flexDirection": "column", "height": "100%", "minHeight": "400px"},
    children=[
        html.Div(
            className="pqc-qc-plot-toolbar",
            style={"flex": "0 0 auto"},
            children=[
                html.Div(
                    className="pqc-qc-metric-wrap",
                    children=[
                        html.Div("Protein IDs", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="protein-intensity-proteins",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="Select one or more proteins",
                            className="pqc-scope-dropdown pqc-protein-intensity-dropdown",
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-qc-xaxis-wrap",
                    children=[
                        html.Div("Metric", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="protein-intensity-metric",
                            options=PROTEIN_METRIC_OPTIONS,
                            value="Reporter intensity corrected",
                            clearable=False,
                            className="pqc-scope-dropdown pqc-protein-intensity-dropdown",
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-qc-xaxis-wrap",
                    children=[
                        html.Div("Single-protein x-axis", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="protein-intensity-x",
                            options=X_AXIS_OPTIONS,
                            value="Index",
                            clearable=False,
                            className="pqc-scope-dropdown pqc-protein-intensity-dropdown",
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-qc-xaxis-wrap",
                    style={"display": "flex", "alignItems": "flex-end"},
                    children=[
                        html.Button(
                            "Download CSV",
                            id="protein-download-btn",
                            className="pqc-anomaly-apply-btn",
                            n_clicks=0,
                        ),
                        dcc.Download(id="protein-download"),
                    ],
                ),
            ],
        ),
        html.Div(
            "Select proteins and a metric to explore protein-level measurements.",
            id="protein-intensity-empty-state",
            className="pqc-empty-state",
            style={"flex": "1 1 auto"},
        ),
        html.Div(id="protein-intensity-alert"),
        dcc.Loading(
            type="circle",
            parent_style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
            style={"display": "flex", "flexDirection": "column", "flex": "1 1 auto", "height": "100%"},
            children=[
                html.Div(
                    [
                        dcc.Graph(
                            id="protein-intensity-figure",
                            responsive=True,
                            style={**GRAPH_STYLE, "display": "none"},
                        ),
                    ],
                    style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                )
            ],
        ),
    ]
)


def callbacks(app):
    @app.callback(
        Output("protein-intensity-proteins", "options"),
        Output("protein-intensity-proteins", "value"),
        Output("protein-intensity-alert", "children", allow_duplicate=True),
        Input("tabs", "value"),
        Input("project", "value"),
        Input("pipeline", "value"),
        Input("qc-scope-data", "data"),
        State("protein-intensity-proteins", "value"),
        prevent_initial_call="initial_duplicate",
    )
    def update_protein_dropdown(tab, project, pipeline, scope_data, current_values, **kwargs):
        current_values = list(current_values or [])
        if tab != "protein_intensity":
            raise PreventUpdate
        if not project or not pipeline:
            return [], [], None

        scope_df = pd.DataFrame(T.dashboard_rows(scope_data))
        if scope_df.empty or ("RawFile" not in scope_df.columns):
            return [], [], None
        raw_files = scope_df["RawFile"].dropna().astype(str).tolist()
        if len(raw_files) == 0:
            return [], [], None

        user = kwargs.get("user")
        protein_result = T.get_protein_names(
            project=project,
            pipeline=pipeline,
            remove_contaminants=True,
            remove_reversed_sequences=True,
            raw_files=raw_files,
            user=user,
        )
        protein_error = protein_result.get("error") if isinstance(protein_result, dict) else None
        protein_df = pd.DataFrame(T.dashboard_result_data(protein_result, {}))
        if protein_df.empty or ("protein_names" not in protein_df.columns):
            alert = None
            if protein_error:
                alert = dbc.Alert(
                    [
                        html.Strong(protein_error.get("message", "Protein name load failed")),
                        html.Div(protein_error.get("detail", "")),
                    ],
                    color="danger",
                )
            return [], [], alert

        protein_values = (
            protein_df["protein_names"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        protein_values = sorted({p for p in protein_values if p != ""}, key=str.lower)
        options = [{"label": p, "value": p} for p in protein_values]
        value_set = {opt["value"] for opt in options}
        selected = [v for v in current_values if v in value_set]
        return options, selected, None

    @app.callback(
        Output("protein-intensity-figure", "figure"),
        Output("protein-intensity-figure", "config"),
        Output("protein-intensity-figure", "style"),
        Output("protein-intensity-empty-state", "children"),
        Output("protein-intensity-empty-state", "style"),
        Output("protein-intensity-alert", "children", allow_duplicate=True),
        Input("tabs", "value"),
        Input("protein-intensity-proteins", "value"),
        Input("protein-intensity-metric", "value"),
        Input("protein-intensity-x", "value"),
        Input("project", "value"),
        Input("pipeline", "value"),
        Input("qc-scope-data", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def plot_protein_intensity(
        tab,
        proteins,
        selected_metric,
        x_axis,
        project,
        pipeline,
        scope_data,
        **kwargs,
    ):
        metric_key = (
            selected_metric
            if selected_metric in PROTEIN_METRICS
            else "Reporter intensity corrected"
        )
        metric_spec = PROTEIN_METRICS[metric_key]
        config = T.gen_figure_config(filename=metric_spec["filename"], editable=False)
        hidden_style = {**GRAPH_STYLE, "display": "none"}
        shown_style = {**GRAPH_STYLE, "display": "block"}

        if tab != "protein_intensity":
            return go.Figure(), config, hidden_style, "Select proteins and a metric to explore protein-level measurements.", {"display": "none"}, None
        if not project or not pipeline:
            return go.Figure(), config, hidden_style, "Select a project and pipeline first.", {"display": "flex"}, None

        proteins = [str(p).strip() for p in (proteins or []) if str(p).strip()]
        proteins = list(dict.fromkeys(proteins))
        if len(proteins) == 0:
            return go.Figure(), config, hidden_style, "Select at least one protein.", {"display": "flex"}, None

        scope_df = pd.DataFrame(T.dashboard_rows(scope_data))
        if scope_df.empty or ("RawFile" not in scope_df.columns):
            scope_error = T.dashboard_scope_error(scope_data)
            alert = None
            message = "No scoped samples available for this view."
            if scope_error:
                alert = dbc.Alert(
                    [
                        html.Strong(scope_error.get("message", "QC scope load failed")),
                        html.Div(scope_error.get("detail", "")),
                    ],
                    color="danger",
                )
                message = "Protein intensity view is unavailable because scoped QC data could not be loaded."
            return go.Figure(), config, hidden_style, message, {"display": "flex"}, alert

        scope_df["RawFile"] = scope_df["RawFile"].astype(str)
        scope_df = scope_df.drop_duplicates(subset=["RawFile"]).reset_index(drop=True)
        if "DateAcquired" in scope_df.columns:
            scope_df["DateAcquired"] = pd.to_datetime(scope_df["DateAcquired"], errors="coerce")
        else:
            scope_df["DateAcquired"] = pd.NaT

        if ("Index" in scope_df.columns) and pd.to_numeric(scope_df["Index"], errors="coerce").notna().any():
            scope_df["Index"] = pd.to_numeric(scope_df["Index"], errors="coerce")
            scope_df = scope_df.sort_values("Index", na_position="last").reset_index(drop=True)
            scope_df["Index"] = pd.RangeIndex(start=1, stop=len(scope_df) + 1)
        else:
            scope_df["Index"] = pd.RangeIndex(start=1, stop=len(scope_df) + 1)

        raw_files = scope_df["RawFile"].tolist()
        user = kwargs.get("user")
        requested_columns = [metric_key]
        payload_result = T.get_protein_groups(
            project=project,
            pipeline=pipeline,
            protein_names=proteins,
            columns=requested_columns,
            data_range=None,
            raw_files=raw_files,
            user=user,
        )
        payload_error = payload_result.get("error") if isinstance(payload_result, dict) else None
        payload = T.dashboard_result_data(payload_result, {})
        data_df = pd.DataFrame(payload) if payload else pd.DataFrame()
        if data_df.empty:
            alert = None
            message = f"No {metric_spec['label'].lower()} values were found for the current selection."
            if payload_error:
                alert = dbc.Alert(
                    [
                        html.Strong(payload_error.get("message", "Protein explorer load failed")),
                        html.Div(payload_error.get("detail", "")),
                    ],
                    color="danger",
                )
                message = "Protein explorer data could not be loaded for the current selection."
            return go.Figure(), config, hidden_style, message, {"display": "flex"}, alert

        protein_col = "Majority protein IDs"
        if protein_col not in data_df.columns:
            return go.Figure(), config, hidden_style, "Protein IDs were not found in the intensity data.", {"display": "flex"}, None
        if "RawFile" not in data_df.columns:
            return go.Figure(), config, hidden_style, "Sample names were not found in the intensity data.", {"display": "flex"}, None

        axis_df = scope_df[["RawFile", "Index", "DateAcquired"]].copy()
        axis_df["RawFileLabel"] = axis_df["RawFile"]
        x_axis = x_axis if x_axis in X_AXIS_LABELS else "Index"
        metric_is_intensity = metric_key == "Reporter intensity corrected"

        if metric_is_intensity:
            intensity_cols = [
                col
                for col in data_df.columns
                if isinstance(col, str) and col.startswith("Reporter intensity corrected ")
            ]
            if len(intensity_cols) == 0:
                return go.Figure(), config, hidden_style, metric_spec["empty_message"], {"display": "flex"}, None

            long_df = data_df[["RawFile", protein_col] + intensity_cols].melt(
                id_vars=["RawFile", protein_col],
                value_vars=intensity_cols,
                var_name="Channel",
                value_name="Intensity",
            )
            long_df["RawFile"] = long_df["RawFile"].astype(str)
            long_df["Intensity"] = pd.to_numeric(long_df["Intensity"], errors="coerce").fillna(0)
            long_df["MetricValue"] = np.log2(long_df["Intensity"] + 1.0)
            long_df["Channel"] = (
                long_df["Channel"]
                .astype(str)
                .str.replace("Reporter intensity corrected ", "", regex=False)
                .str.strip()
            )
            long_df["ChannelNo"] = pd.to_numeric(long_df["Channel"], errors="coerce")
            long_df = long_df[long_df["RawFile"].isin(raw_files)]
            if long_df.empty:
                return go.Figure(), config, hidden_style, "No reporter intensity records match the selected samples.", {"display": "flex"}, None
            long_df = long_df.merge(axis_df, on="RawFile", how="left")
        else:
            if metric_key not in data_df.columns:
                return go.Figure(), config, hidden_style, metric_spec["empty_message"], {"display": "flex"}, None
            long_df = data_df[["RawFile", protein_col, metric_key]].copy()
            long_df["RawFile"] = long_df["RawFile"].astype(str)
            long_df["MetricValue"] = pd.to_numeric(long_df[metric_key], errors="coerce")
            long_df = long_df.dropna(subset=["MetricValue"])
            long_df = long_df[long_df["RawFile"].isin(raw_files)]
            if long_df.empty:
                return go.Figure(), config, hidden_style, metric_spec["empty_message"], {"display": "flex"}, None
            long_df = long_df.merge(axis_df, on="RawFile", how="left")

        if len(proteins) == 1:
            protein_name = proteins[0]
            single = long_df[long_df[protein_col] == protein_name].copy()
            if single.empty:
                return go.Figure(), config, hidden_style, f"The selected protein has no {metric_spec['label'].lower()} values in this scope.", {"display": "flex"}, None

            axis_mode = x_axis if x_axis in {"Index", "RawFile", "DateAcquired"} else "Index"
            run_order = {raw: idx for idx, raw in enumerate(raw_files)}
            single["run_idx"] = single["RawFile"].map(run_order)

            def _sample_axis_label(row):
                if axis_mode == "RawFile":
                    return str(row.get("RawFileLabel", "Sample"))
                if axis_mode == "DateAcquired":
                    dt = pd.to_datetime(row.get("DateAcquired"), errors="coerce")
                    if pd.notna(dt):
                        return dt.strftime("%Y-%m-%d")
                return f"Sample {int(row.get('run_idx', 0)) + 1}"

            if metric_is_intensity:
                single = (
                    single.groupby(
                        ["RawFile", "Channel", "ChannelNo", "Index", "DateAcquired", "RawFileLabel", "run_idx"],
                        as_index=False,
                    )[["Intensity", "MetricValue"]]
                    .median()
                )
                single = single.sort_values(["run_idx", "ChannelNo"], na_position="last").reset_index(drop=True)
                single["sample_label"] = single.apply(_sample_axis_label, axis=1)
                single["x_label"] = single.apply(
                    lambda row: f"{row['RawFile']} / TMT{int(row['ChannelNo'])}"
                    if pd.notna(row["ChannelNo"])
                    else f"{row['RawFile']} / {row['Channel']}",
                    axis=1,
                )
                single["x_pos"] = np.arange(1, len(single) + 1, dtype=int)
                sample_tick_df = (
                    single.groupby(["run_idx", "sample_label"], as_index=False)["x_pos"]
                    .mean()
                    .sort_values("run_idx")
                )
                customdata = np.stack(
                    [
                        single["RawFile"].astype(str).values,
                        single["Channel"].astype(str).values,
                        single["Intensity"].astype(float).values,
                    ],
                    axis=1,
                )
                hovertemplate = (
                    "<b>%{text}</b><br>"
                    "log2(1+intensity): %{y:.2f}<br>"
                    "Raw file: %{customdata[0]}<br>"
                    "Channel: %{customdata[1]}<br>"
                    "Intensity: %{customdata[2]:.2f}<extra></extra>"
                )
            else:
                single = (
                    single.groupby(
                        ["RawFile", "Index", "DateAcquired", "RawFileLabel", "run_idx"],
                        as_index=False,
                    )["MetricValue"]
                    .median()
                )
                single = single.sort_values("run_idx", na_position="last").reset_index(drop=True)
                single["sample_label"] = single.apply(_sample_axis_label, axis=1)
                single["x_label"] = single["RawFileLabel"].astype(str)
                single["x_pos"] = np.arange(1, len(single) + 1, dtype=int)
                sample_tick_df = single[["x_pos", "sample_label"]].copy()
                customdata = np.stack(
                    [
                        single["RawFile"].astype(str).values,
                        single["MetricValue"].astype(float).values,
                    ],
                    axis=1,
                )
                hovertemplate = (
                    "<b>%{text}</b><br>"
                    + f"{metric_spec['y_title']}: "
                    + "%{y:.2f}<br>"
                    "Raw file: %{customdata[0]}<extra></extra>"
                )

            fig = go.Figure(
                data=[
                    go.Scatter(
                        x=single["x_pos"],
                        y=single["MetricValue"],
                        mode="lines+markers",
                        showlegend=False,
                        marker=dict(
                            size=8,
                            color="#06b6d4",
                            line=dict(width=1, color="#ffffff"),
                        ),
                        line=dict(width=2, color="rgba(6, 182, 212, 0.5)"),
                        text=single["x_label"],
                        customdata=customdata,
                        hovertemplate=hovertemplate,
                    )
                ]
            )
        else:
            multi = long_df[long_df[protein_col].isin(proteins)].copy()
            if multi.empty:
                return go.Figure(), config, hidden_style, f"No {metric_spec['label'].lower()} values were found for the selected proteins.", {"display": "flex"}, None

            fig = go.Figure()
            palette = px.colors.qualitative.Pastel
            for idx, protein_name in enumerate(proteins):
                protein_df = multi[multi[protein_col] == protein_name]
                if protein_df.empty:
                    continue
                if metric_is_intensity:
                    customdata = np.stack(
                        [
                            protein_df["RawFile"].astype(str).values,
                            protein_df["Channel"].astype(str).values,
                            protein_df["Intensity"].astype(float).values,
                        ],
                        axis=1,
                    )
                    hovertemplate = (
                        "<b>%{x}</b><br>"
                        "log2(1+intensity): %{y:.2f}<br>"
                        "Raw file: %{customdata[0]}<br>"
                        "Channel: %{customdata[1]}<br>"
                        "Intensity: %{customdata[2]:.2f}<extra></extra>"
                    )
                else:
                    customdata = np.stack(
                        [
                            protein_df["RawFile"].astype(str).values,
                            protein_df["MetricValue"].astype(float).values,
                        ],
                        axis=1,
                    )
                    hovertemplate = (
                        "<b>%{x}</b><br>"
                        + f"{metric_spec['y_title']}: "
                        + "%{y:.2f}<br>"
                        "Raw file: %{customdata[0]}<extra></extra>"
                    )
                fig.add_trace(
                    go.Violin(
                        x=np.repeat(protein_name, len(protein_df)),
                        y=protein_df["MetricValue"],
                        name=protein_name,
                        side="positive",
                        box_visible=False,
                        meanline_visible=False,
                        points="all",
                        pointpos=-0.4,
                        jitter=0.24,
                        marker=dict(
                            size=6,
                            opacity=1,
                            color=palette[idx % len(palette)],
                        ),
                        line=dict(width=0),
                        fillcolor=palette[idx % len(palette)],
                        opacity=1,
                        customdata=customdata,
                        hovertemplate=hovertemplate,
                    )
                )
        fig.update_layout(
            hovermode="closest",
            margin=dict(l=32, r=20, b=40, t=24, pad=0),
            font=C.figure_font,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            yaxis={"automargin": True},
            xaxis={"automargin": True},
            showlegend=False,
        )
        fig.update_xaxes(
            title_text=X_AXIS_LABELS.get(x_axis, "Sample") if len(proteins) == 1 else "Proteins",
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor="#e2e8ed",
            automargin=True,
        )
        if len(proteins) == 1:
            n_points = int(single["x_pos"].max()) if len(single) > 0 else 1
            tv = sample_tick_df["x_pos"].tolist()
            tt = sample_tick_df["sample_label"].tolist()
            tv, tt = _thin_ticks(tv, tt)
            fig.update_xaxes(
                tickmode="array",
                tickvals=tv,
                ticktext=tt,
                tickangle=-90,
                title_standoff=20,
                range=[0.5, float(n_points) + 0.5],
            )
        else:
            y_max = pd.to_numeric(multi["MetricValue"], errors="coerce").max()
            y_max = 1.0 if pd.isna(y_max) else float(y_max)
            fig.update_yaxes(range=[-0.35, y_max + 0.8])
        fig.update_yaxes(
            title_text=metric_spec["y_title"],
            showgrid=True,
            gridcolor="#f1f5f7",
            zeroline=False,
            showline=True,
            linecolor="#e2e8ed",
            rangemode="tozero",
            title_standoff=30,
            automargin=True,
        )

        return fig, config, shown_style, "", {"display": "none"}, None

    @app.callback(
        Output("protein-download", "data"),
        Input("protein-download-btn", "n_clicks"),
        State("protein-intensity-proteins", "value"),
        State("protein-intensity-metric", "value"),
        State("project", "value"),
        State("pipeline", "value"),
        State("qc-scope-data", "data"),
    )
    def download_protein_data(n_clicks, proteins, selected_metric, project, pipeline, scope_data, **kwargs):
        if not n_clicks:
            raise PreventUpdate
        proteins = [str(p).strip() for p in (proteins or []) if str(p).strip()]
        proteins = list(dict.fromkeys(proteins))
        if not proteins or not project or not pipeline:
            raise PreventUpdate

        scope_df = pd.DataFrame(T.dashboard_rows(scope_data))
        if scope_df.empty or "RawFile" not in scope_df.columns:
            raise PreventUpdate
        raw_files = scope_df["RawFile"].dropna().astype(str).tolist()
        if not raw_files:
            raise PreventUpdate

        metric_key = (
            selected_metric
            if selected_metric in PROTEIN_METRICS
            else "Reporter intensity corrected"
        )
        metric_spec = PROTEIN_METRICS[metric_key]
        user = kwargs.get("user")
        requested_columns = [metric_key]
        payload_result = T.get_protein_groups(
            project=project,
            pipeline=pipeline,
            protein_names=proteins,
            columns=requested_columns,
            data_range=None,
            raw_files=raw_files,
            user=user,
        )
        payload = T.dashboard_result_data(payload_result, {})
        data_df = pd.DataFrame(payload) if payload else pd.DataFrame()
        if data_df.empty:
            raise PreventUpdate

        # For reporter intensity, expand all channel columns
        protein_col = "Majority protein IDs"
        if metric_key == "Reporter intensity corrected":
            intensity_cols = [
                col for col in data_df.columns
                if isinstance(col, str) and col.startswith("Reporter intensity corrected ")
            ]
            if intensity_cols:
                keep_cols = ["RawFile", protein_col] + intensity_cols
                keep_cols = [c for c in keep_cols if c in data_df.columns]
                data_df = data_df[keep_cols]
        else:
            keep_cols = ["RawFile", protein_col, metric_key]
            keep_cols = [c for c in keep_cols if c in data_df.columns]
            data_df = data_df[keep_cols]

        filename = f"protein-explorer-{metric_spec.get('filename', 'data')}-{project or 'project'}-{pipeline or 'pipeline'}.csv"
        return dcc.send_data_frame(data_df.to_csv, filename, index=False)
