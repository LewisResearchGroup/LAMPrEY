import json
import hashlib
import logging
import re
import pandas as pd
from dash import dcc, html

from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

import plotly.graph_objects as go

from dashboards.dashboards.dashboard import config as C
from dashboards.dashboards.dashboard import tools as T
from omics.proteomics.maxquant.quality_control import (
    is_integer_metric_name,
    metric_display_precision,
)

# Keep the graph responsive
GRAPH_STYLE = {
    "width": "100%",
    "height": "100%",
    "flex": "1 1 auto",
    "minHeight": "0",
}

METRIC_LABELS = {
    "N_peptides": "Peptides Identified",
    "N_protein_groups": "Protein Groups Identified",
    "MS/MS Identified [%]": "MS/MS Identified (%)",
    "Oxidations [%]": "Oxidations (%)",
    "N_missed_cleavages_eq_1 [%]": "Missed Cleavages Eq1 (%)",
    "Protein_score_median": "Protein Score Median",
    "Protein_score_mean": "Protein Score Mean",
    "Protein_qvalue_median": "Protein Q-value Median",
    "Protein_qvalue_lt_0_01 [%]": "Proteins Q-value < 0.01 (%)",
    "Protein_peptides_median": "Protein Peptides Median",
    "Protein_unique_peptides_median": "Protein Unique Peptides Median",
    "Protein_razor_unique_peptides_median": "Protein Razor+Unique Peptides Median",
    "Protein_unique_peptides_eq_1 [%]": "Proteins With 1 Unique Peptide (%)",
    "Protein_msms_count_median": "Protein MS/MS Count Median",
    "Protein_unique_seq_cov_median [%]": "Protein Unique Seq Coverage Median (%)",
    "Peptide_score_median": "Peptide Score Median",
    "Peptide_score_mean": "Peptide Score Mean",
    "Peptide_PEP_median": "Peptide PEP Median",
    "Peptide_PEP_lt_0_01 [%]": "Peptides PEP < 0.01 (%)",
    "Peptide_length_median": "Peptide Length Median",
    "Peptide_msms_count_median": "Peptide MS/MS Count Median",
    "Peptide_unique_groups [%]": "Unique Peptides In Groups (%)",
    "Peptide_unique_proteins [%]": "Unique Peptides In Proteins (%)",
    "Uncalibrated - Calibrated m/z [ppm] (ave)": "Delta m/z (ppm, avg)",
    # Group-specific QC1/QC2 metrics are temporarily disabled.
    # "calibrated_retention_time_qc1": "Calibrated RT QC1",
    # "calibrated_retention_time_qc2": "Calibrated RT QC2",
    "__tmt_peptides_per_sample__": "Peptides per TMT Sample",
    "__tmt_protein_groups_per_sample__": "Protein Groups per TMT Sample",
}

X_AXIS_LABELS = {
    "Index": "Sample Index",
    "RawFile": "Sample",
    "DateAcquired": "Acquisition Date",
}

x_options = [dict(label=X_AXIS_LABELS[x], value=x) for x in X_AXIS_LABELS]

metric_options = [
    {"label": METRIC_LABELS[k], "value": k}
    for k in [
        "N_peptides",
        "__tmt_peptides_per_sample__",
        "N_protein_groups",
        "__tmt_protein_groups_per_sample__",
        "MS/MS Identified [%]",
        "Oxidations [%]",
        "N_missed_cleavages_eq_1 [%]",
        "Protein_score_median",
        "Protein_score_mean",
        "Protein_qvalue_median",
        "Protein_qvalue_lt_0_01 [%]",
        "Protein_peptides_median",
        "Protein_unique_peptides_median",
        "Protein_razor_unique_peptides_median",
        "Protein_unique_peptides_eq_1 [%]",
        "Protein_msms_count_median",
        "Protein_unique_seq_cov_median [%]",
        "Peptide_score_median",
        "Peptide_score_mean",
        "Peptide_PEP_median",
        "Peptide_PEP_lt_0_01 [%]",
        "Peptide_length_median",
        "Peptide_msms_count_median",
        "Peptide_unique_groups [%]",
        "Peptide_unique_proteins [%]",
        "Uncalibrated - Calibrated m/z [ppm] (ave)",
        # Group-specific QC1/QC2 metrics are temporarily disabled.
        # "calibrated_retention_time_qc1",
        # "calibrated_retention_time_qc2",
    ]
]

BUTTON_STYLE = {
    "padding": "8px 18px",
    "borderRadius": "8px",
    "fontWeight": 600,
    "fontSize": "14px",
    "border": "1px solid #a5f3fc",
    "background": "#ecfeff",
    "color": "#0891b2",
    "cursor": "pointer",
}

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
                        html.Div("QC Metric", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="qc-metric",
                            multi=False,
                            options=metric_options,
                            value="N_peptides",
                            className="pqc-metric-dropdown",
                            clearable=False,
                        ),
                    ],
                ),
                html.Div(
                    className="pqc-qc-xaxis-wrap",
                    children=[
                        html.Div("X-Axis", className="pqc-field-label"),
                        dcc.Dropdown(
                            id="x",
                            options=x_options,
                            value="Index",
                            className="pqc-metric-dropdown",
                            clearable=False,
                        ),
                    ],
                ),
            ],
        ),
        html.Div(
            "No QC plot data available for this scope.",
            id="qc-empty-state",
            className="pqc-empty-state",
            style={"flex": "1 1 auto"}
        ),
        dcc.Loading(
            type="circle",
            parent_style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
            style={"display": "flex", "flexDirection": "column", "flex": "1 1 auto", "height": "100%"},
            children=[
                html.Div(
                    [
                        dcc.Graph(
                            id="qc-figure",
                            responsive=True,
                            style={**GRAPH_STYLE, "display": "none"},
                        ),
                    ],
                    style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                )
            ]
        ),
    ]
)


def callbacks(app):
    highlight_marker_color = "#ef4444"
    highlight_marker_line_color = "#7f1d1d"

    def _sample_label_series(df):
        if "SampleLabel" in df.columns:
            return df["SampleLabel"].astype(str)
        if "RawFile" in df.columns:
            return df["RawFile"].astype(str)
        return df.index.astype(str)

    def _scope_sig(scope_data):
        return hashlib.md5(
            json.dumps(scope_data or {}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def _highlight_run_keys(scope_data, proposal, df):
        if not proposal or df.empty:
            return set()
        if proposal.get("scope_sig") != _scope_sig(scope_data):
            return set()
        run_keys = set(proposal.get("run_keys_to_flag") or [])
        if not run_keys:
            return set()
        if "RunKey" in df.columns:
            available = set(df["RunKey"].astype(str))
            return run_keys.intersection(available)
        if "RawFile" in df.columns:
            available = set(df["RawFile"].astype(str))
            return run_keys.intersection(available)
        return set()

    @app.callback(
        Output("qc-figure", "figure"),
        Output("qc-figure", "config"),
        Output("qc-figure", "style"),
        Output("qc-empty-state", "style"),
        Input("tabs", "value"),
        Input("qc-scope-data", "data"),
        Input("qc-metric", "value"),
        Input("x", "value"),
        Input("anomaly-proposed-flags", "data"),
    )
    def plot_qc_figure(tab, data_in, metric_in, x_in, anomaly_proposal):
        """Creates the QC trend plot figure."""
        if tab != "quality_control":
            raise PreventUpdate
        data = data_in
        if data is None:
            raise PreventUpdate
        x = x_in or "RawFile"
        selected_metric = metric_in or "N_peptides"

        df = pd.DataFrame(T.dashboard_rows(data))
        if df.empty:
            return (
                go.Figure(),
                T.gen_figure_config(filename="QC-barplot", editable=False),
                {**GRAPH_STYLE, "display": "none"},
                {"display": "flex", "flex": "1 1 auto"},
            )

        assert pd.value_counts(df.columns).max() == 1, pd.value_counts(df.columns)

        if "DateAcquired" in df.columns:
            df["DateAcquired"] = pd.to_datetime(df["DateAcquired"], errors="coerce")
        else:
            df["DateAcquired"] = pd.NaT

        highlight_run_keys = _highlight_run_keys(data_in, anomaly_proposal, df)

        if x not in df.columns:
            x = "Index" if "Index" in df.columns else "RawFile"
        if x == "Index" and "Index" in df.columns:
            df = df.sort_values("Index", na_position="last").reset_index(drop=True)
            df["Index"] = pd.RangeIndex(start=1, stop=len(df) + 1)

        if selected_metric not in df.columns:
            synthetic_metric_cols = {
                "__tmt_peptides_per_sample__": (
                    r"^TMT\d+_peptide_count$",
                    "Peptide Count",
                ),
                "__tmt_protein_groups_per_sample__": (
                    r"^TMT\d+_protein_group_count$",
                    "Protein Group Count",
                ),
            }
            if selected_metric in synthetic_metric_cols:
                tmt_pattern, y_axis_title = synthetic_metric_cols[selected_metric]
                tmt_cols = sorted(
                    [c for c in df.columns if re.match(tmt_pattern, str(c))],
                    key=lambda c: int(re.search(r"\d+", str(c)).group(0)),
                )
                if len(tmt_cols) == 0:
                    return (
                        go.Figure(),
                        T.gen_figure_config(filename="QC-trends", editable=False),
                        {**GRAPH_STYLE, "display": "none"},
                        {"display": "flex", "flex": "1 1 auto"},
                    )

                if "Index" in df.columns:
                    df = df.sort_values("Index", na_position="last").reset_index(drop=True)
                else:
                    df = df.reset_index(drop=True)
                if "RawFile" not in df.columns:
                    df["RawFile"] = [f"Run {i+1}" for i in range(len(df))]

                axis_mode = x if x in {"Index", "RawFile", "DateAcquired"} else "Index"

                def _sample_axis_label(row, run_idx):
                    if axis_mode == "RawFile":
                        return str(row.get("RawFile", f"Sample {run_idx + 1}"))
                    if axis_mode == "DateAcquired":
                        dt_value = row.get("DateAcquired")
                        dt = pd.to_datetime(dt_value, errors="coerce")
                        if pd.notna(dt):
                            return dt.strftime("%Y-%m-%d")
                    return f"Sample {run_idx + 1}"

                expanded_rows = []
                for run_idx, row in df.iterrows():
                    run_label = str(row.get("RawFile", f"Run {run_idx + 1}"))
                    sample_label = _sample_axis_label(row, run_idx)
                    for col in tmt_cols:
                        channel_no = int("".join(ch for ch in str(col) if ch.isdigit()))
                        value = pd.to_numeric(
                            pd.Series([row.get(col)]), errors="coerce"
                        ).iloc[0]
                        value = 0.0 if pd.isna(value) else float(value)
                        expanded_rows.append(
                            {
                                "x_label": f"{run_label} / TMT{channel_no}",
                                "x_label_short": f"R{run_idx + 1}-T{channel_no}",
                                "sample_label": sample_label,
                                "run_label": run_label,
                                "run_key": str(row.get("RunKey", run_label)),
                                "channel_no": channel_no,
                                "value": value,
                                "run_idx": int(run_idx),
                            }
                        )
                long_df = pd.DataFrame(expanded_rows)
                if long_df.empty:
                    return (
                        go.Figure(),
                        T.gen_figure_config(filename="QC-trends", editable=False),
                        {**GRAPH_STYLE, "display": "none"},
                        {"display": "flex", "flex": "1 1 auto"},
                    )

                metric_label = METRIC_LABELS.get(selected_metric, selected_metric)
                y_max = float(pd.to_numeric(long_df["value"], errors="coerce").max() or 0.0)
                y_upper = 1.0 if y_max <= 0 else y_max * 1.03
                long_df["x_pos"] = range(1, len(long_df) + 1)
                sample_tick_df = (
                    long_df.groupby(["run_idx", "sample_label"], as_index=False)["x_pos"]
                    .mean()
                    .sort_values("run_idx")
                )
                tickvals = sample_tick_df["x_pos"].tolist()
                ticktext = sample_tick_df["sample_label"].tolist()

                figure_data = [
                    go.Scatter(
                        x=long_df["x_pos"],
                        y=long_df["value"],
                        mode="lines+markers",
                        showlegend=False,
                        marker=dict(
                            size=6,
                            color="#06b6d4",
                            line=dict(width=0.8, color="#ffffff"),
                        ),
                        line=dict(width=1.6, color="rgba(6, 182, 212, 0.5)"),
                        text=long_df["x_label"],
                        customdata=long_df["run_idx"],
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            + f"{metric_label}: "
                            + "%{y:.0f}<extra></extra>"
                        ),
                    )
                ]
                highlight_mask = long_df["run_key"].isin(highlight_run_keys)
                if highlight_mask.any():
                    figure_data.append(
                        go.Scatter(
                            x=long_df.loc[highlight_mask, "x_pos"],
                            y=long_df.loc[highlight_mask, "value"],
                            mode="markers",
                            showlegend=False,
                            marker=dict(
                                size=9,
                                color=highlight_marker_color,
                                line=dict(width=1.2, color=highlight_marker_line_color),
                            ),
                            text=long_df.loc[highlight_mask, "x_label"],
                            customdata=long_df.loc[highlight_mask, "run_idx"],
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                + f"{metric_label}: "
                                + "%{y:.0f}<br>"
                                + "Anomaly candidate<extra></extra>"
                            ),
                        )
                    )

                fig = go.Figure(data=figure_data)
                fig.update_layout(
                    hovermode="closest",
                    hoverlabel_namelength=-1,
                    showlegend=False,
                    margin=dict(l=32, r=20, b=40, t=24, pad=0),
                    font=C.figure_font,
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    yaxis={"automargin": True},
                    xaxis={"automargin": True},
                )
                fig.update_xaxes(
                    title_text=X_AXIS_LABELS.get(axis_mode, "Sample"),
                    tickmode="array",
                    tickvals=tickvals,
                    ticktext=ticktext,
                    showgrid=False,
                    zeroline=False,
                    showline=True,
                    linecolor="#e2e8ed",
                    tickangle=-90,
                    title_standoff=20,
                )
                # Keep synthetic index axes anchored at 1 to avoid negative
                # autorange padding ticks on the left side.
                if len(long_df) > 0:
                    fig.update_xaxes(range=[0.5, float(len(long_df)) + 0.5])
                fig.update_yaxes(
                    title_text=y_axis_title,
                    showgrid=True,
                    gridcolor="#f1f5f7",
                    zeroline=False,
                    showline=True,
                    linecolor="#e2e8ed",
                    range=[0, y_upper],
                    title_standoff=30,
                )
                config = T.gen_figure_config(filename="QC-trends", editable=False)
                graph_style = {**GRAPH_STYLE, "display": "block"}
                return fig, config, graph_style, {"display": "none", "flex": "1 1 auto"}

            return (
                go.Figure(),
                T.gen_figure_config(filename="QC-trends", editable=False),
                {**GRAPH_STYLE, "display": "none"},
                {"display": "flex", "flex": "1 1 auto"},
            )
        # Keep all samples visible by imputing missing points as zero.
        y_series = pd.to_numeric(df[selected_metric], errors="coerce").fillna(0)
        y_max = float(y_series.max() or 0.0)
        y_upper = 1.0 if y_max <= 0 else y_max * 1.03
        metric_label = METRIC_LABELS.get(selected_metric, selected_metric)
        x_axis_label = X_AXIS_LABELS.get(x, x)
        y_precision = (
            0
            if is_integer_metric_name(selected_metric)
            else metric_display_precision(selected_metric)
        )
        y_hover_format = f".{y_precision}f"

        raw_labels = (
            df["RawFile"].astype(str)
            if "RawFile" in df.columns
            else df.index.astype(str)
        )
        sample_labels = _sample_label_series(df)
        acquired = df["DateAcquired"].astype(str).replace("NaT", "N/A")
        x_values = sample_labels if x == "RawFile" else df[x]
        figure_data = [
            go.Scatter(
                x=x_values,
                y=y_series,
                name=metric_label,
                mode="lines+markers",
                line=dict(width=2.5, color="#06b6d4", shape="linear"),
                marker=dict(size=8, color="#06b6d4", line=dict(width=1.5, color="#ffffff")),
                customdata=df.index.to_list(),
                hovertext=sample_labels + "<br>" + acquired,
                text=None if x == "RawFile" else sample_labels,
                hovertemplate=(
                    "<b>%{hovertext}</b><br>"
                    + f"{metric_label}: "
                    + f"%{{y:{y_hover_format}}}<extra></extra>"
                ),
            )
        ]
        highlight_series = (
            df["RunKey"].astype(str).isin(highlight_run_keys)
            if "RunKey" in df.columns
            else raw_labels.isin(highlight_run_keys)
        )
        if highlight_series.any():
            figure_data.append(
                go.Scatter(
                    x=x_values[highlight_series],
                    y=y_series[highlight_series],
                    mode="markers",
                    showlegend=False,
                    marker=dict(
                        size=11,
                        color=highlight_marker_color,
                        line=dict(width=1.6, color=highlight_marker_line_color),
                    ),
                    customdata=df.index[highlight_series].to_list(),
                    hovertext=(sample_labels[highlight_series] + "<br>" + acquired[highlight_series]),
                    text=None if x == "RawFile" else sample_labels[highlight_series],
                    hovertemplate=(
                        "<b>%{hovertext}</b><br>"
                        + f"{metric_label}: "
                        + f"%{{y:{y_hover_format}}}<br>"
                        + "Anomaly candidate<extra></extra>"
                    ),
                )
            )
        fig = go.Figure(data=figure_data)

        fig.update_layout(
            hovermode="closest",
            hoverlabel_namelength=-1,
            showlegend=False,
            margin=dict(l=32, r=20, b=40, t=24, pad=0),
            font=C.figure_font,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            yaxis={"automargin": True},
            xaxis={"automargin": True},
        )

        fig.update_traces(marker_line_width=1, opacity=0.95)

        logging.info(f"QC plot built for metric {selected_metric} with height {fig.layout.height}")

        fig.update_xaxes(
            title_text=x_axis_label,
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor="#e2e8ed",
            tickangle=-90,
            title_standoff=20,
            automargin=True,
        )
        if x == "Index":
            index_max = int(pd.to_numeric(df["Index"], errors="coerce").max() or 0)
            fig.update_xaxes(
                dtick=1,
                tick0=1,
                tickformat="d",
                range=[0.5, float(max(1, index_max)) + 0.5],
            )
        elif x == "RawFile":
            # Tighten the x-axis range for categorical labels so there is
            # no blank padding at the start/end of the plot area.
            n_samples = len(x_values)
            if n_samples > 0:
                fig.update_xaxes(range=[-0.5, n_samples - 0.5])
        fig.update_yaxes(
            title_text=metric_label,
            showgrid=True,
            gridcolor="#f1f5f7",
            zeroline=False,
            showline=True,
            linecolor="#e2e8ed",
            range=[0, y_upper],
            title_standoff=30,
            automargin=True,
            tickformat=",d" if is_integer_metric_name(selected_metric) else None,
        )

        config = T.gen_figure_config(filename="QC-trends", editable=False)

        graph_style = {**GRAPH_STYLE, "display": "block"}

        return fig, config, graph_style, {"display": "none", "flex": "1 1 auto"}
