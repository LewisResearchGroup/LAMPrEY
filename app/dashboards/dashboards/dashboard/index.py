import os
import re
import pandas as pd
import numpy as np
from pathlib import Path as P

import dash
from dash import html, dcc
from dash import dash_table as dt
import dash_bootstrap_components as dbc

import panel as pn

pn.extension("plotly")

from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from omics.plotly_tools import (
    set_template,
)
from omics.proteomics import ProteomicsQC
from omics.proteomics.maxquant.quality_control import (
    is_integer_metric_name,
    metric_display_precision,
)


from dashboards.dashboards.dashboard.tools import list_to_dropdown_options
from dashboards.dashboards.dashboard import tools as T

set_template()


def _detected_tmt_qc_columns(columns):
    pattern = re.compile(
        r"^TMT\d+_(missing_values|peptide_count|protein_group_count)$"
    )
    detected = [c for c in columns if pattern.match(str(c))]
    return sorted(
        detected,
        key=lambda c: (
            int(re.search(r"\d+", str(c)).group(0)),
            str(c),
        ),
    )


def _with_sample_labels(df):
    if df is None or df.empty or "RawFile" not in df.columns:
        return df

    df = df.copy()
    raw_names = df["RawFile"].fillna("").astype(str).str.strip()
    duplicate_counts = raw_names[raw_names != ""].value_counts()

    labels = []
    for row_idx, row in df.iterrows():
        raw_name = str(row.get("RawFile") or "").strip() or f"Sample {row_idx + 1}"
        run_key = str(row.get("RunKey") or "").strip()
        if duplicate_counts.get(raw_name, 0) > 1 and run_key:
            labels.append(f"{raw_name} [{run_key}]")
        else:
            labels.append(raw_name)

    df["SampleLabel"] = labels
    return df


if __name__ == "__main__":
    app = dash.Dash(
        __name__,
        external_stylesheets=["/static/css/dashboard.css"],
    )
    from dashboards.dashboards.dashboard import (
        anomaly,
        config as C,
        protein_intensity,
        quality_control,
        tools as T,
    )

    app.config.suppress_callback_exceptions = True
else:
    from django_plotly_dash import DjangoDash
    from dashboards.dashboards.dashboard import (
        anomaly,
        config as C,
        protein_intensity,
        quality_control,
        tools as T,
    )

    app = DjangoDash(
        "dashboard",
        add_bootstrap_links=True,
        suppress_callback_exceptions=True,
        external_stylesheets=[
            "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
            "/static/css/dashboard.css",
        ],
    )

timeout = 360


protein_table_default_cols = []
TAB_PANEL_STYLE = {
    "display": "none",
    "flex": "1 1 auto",
    "flexDirection": "column",
    "minHeight": "0",
}
BUTTON_STYLE = {
    "padding": "8px 18px",
    "backgroundColor": "#ecfeff",
    "color": "#0891b2",
    "border": "1px solid #a5f3fc",
    "borderRadius": "8px",
    "cursor": "pointer",
    "fontWeight": 600,
    "fontSize": "14px",
    "transition": "all 150ms ease",
}

layout = html.Div(
    [
        dcc.Loading(dcc.Store(id="store"), type="circle"),
        dcc.Store(id="qc-scope-data"),
        dcc.Store(id="qc-admin-session", data=False),
        dcc.Store(id="qc-user-uid", data=None),
        dcc.Store(id="qc-uploader-options", data=[]),
        html.Button("", id="B_update", className="pqc-hidden-trigger"),
        html.Div(
            className="pqc-layout",
            children=[
                html.Div(id="pqc-dashboard-alert"),
                html.Div(
                    className="pqc-main-grid",
                    children=[
                        html.Div(
                            className="pqc-panel pqc-insights-panel",
                            children=[
                                html.Div(
                                    className="pqc-panel-header",
                                    children=[
                                        html.H3("Key Metrics", className="pqc-panel-title"),
                                        html.Div(
                                            "0 samples in current selection",
                                            id="pqc-scope-subtitle",
                                            className="pqc-scope-subtitle",
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="pqc-scope-grid pqc-scope-grid-inside",
                                    children=[
                                        html.Div(
                                            className="pqc-scope-field",
                                            children=[
                                                html.Label("Project", className="pqc-field-label"),
                                                dcc.Dropdown(
                                                    id="project",
                                                    options=[],
                                                    value=None,
                                                    className="pqc-scope-dropdown",
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-scope-field",
                                            children=[
                                                html.Label("Pipeline", className="pqc-field-label"),
                                                dcc.Dropdown(
                                                    id="pipeline",
                                                    options=[],
                                                    value=None,
                                                    className="pqc-scope-dropdown",
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            id="pqc-scope-user-field",
                                            className="pqc-scope-field",
                                            style={"display": "block"},
                                            children=[
                                                html.Label("User", className="pqc-field-label"),
                                                dcc.Dropdown(
                                                    id="scope-uploader",
                                                    options=[{"label": "All users", "value": "__all__"}],
                                                    value="__all__",
                                                    className="pqc-scope-dropdown",
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="pqc-kpi-grid",
                                    children=[
                                        html.Div(
                                            className="pqc-kpi-card pqc-kpi-primary pqc-kpi-samples-card",
                                            children=[
                                                html.Div("Runs", className="pqc-kpi-label"),
                                                html.Div("0", id="kpi-samples", className="pqc-kpi-value"),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card pqc-kpi-primary pqc-kpi-samples-card",
                                            children=[
                                                html.Div("TMT Samples", className="pqc-kpi-label"),
                                                html.Div("0", id="kpi-tmt-samples", className="pqc-kpi-value"),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div("Median Protein Groups", className="pqc-kpi-label"),
                                                html.Div(
                                                    "--",
                                                    id="kpi-median-protein-groups",
                                                    className="pqc-kpi-value",
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div(
                                                    ["Median", html.Br(), "Peptides"],
                                                    className="pqc-kpi-label",
                                                ),
                                                html.Div("--", id="kpi-median-peptides", className="pqc-kpi-value"),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div("Median MS/MS Identified [%]", className="pqc-kpi-label"),
                                                html.Div("--", id="kpi-median-msms", className="pqc-kpi-value"),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div(
                                                    "Median Miss Cleav Eq1 [%]",
                                                    className="pqc-kpi-label",
                                                ),
                                                html.Div(
                                                    "--",
                                                    id="kpi-median-missed-cleavages",
                                                    className="pqc-kpi-value",
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div("Median Oxidations [%]", className="pqc-kpi-label"),
                                                html.Div("--", id="kpi-median-oxidations", className="pqc-kpi-value"),
                                            ],
                                        ),
                                        html.Div(
                                            className="pqc-kpi-card",
                                            children=[
                                                html.Div(
                                                    "Median Delta m/z [ppm]",
                                                    className="pqc-kpi-label",
                                                ),
                                                html.Div(
                                                    "--",
                                                    id="kpi-median-mz-delta",
                                                    className="pqc-kpi-value",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            className="pqc-panel pqc-workspace-panel",
                            children=[
                                dcc.Tabs(
                                    id="tabs",
                                    value="quality_control",
                                    className="pqc-tabs",
                                    children=[
                                        dcc.Tab(
                                            id="tab-qc",
                                            label="Quality Control",
                                            value="quality_control",
                                        ),
                                        dcc.Tab(
                                            id="tab-anomaly",
                                            label="Anomaly detection",
                                            value="anomaly",
                                        ),
                                        dcc.Tab(
                                            id="tab-protein-intensity",
                                            label="Protein Explorer",
                                            value="protein_intensity",
                                        ),
                                    ],
                                ),
                                dcc.Loading(
                                    id="pqc-workspace-loading",
                                    type="circle",
                                    parent_style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                                    style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                                    children=html.Div(
                                        style={"flex": "1 1 auto", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                                        children=[
                                            html.Div(
                                                id="qc-loading-probe",
                                                className="pqc-hidden-trigger",
                                            ),
                                            html.Div(
                                                id="tabs-content",
                                                className="pqc-canvas",
                                                style={"display": "flex", "flexDirection": "column", "minHeight": "0"},
                                                children=[
                                                    html.Div(
                                                        id="tab-panel-quality-control",
                                                        style={
                                                            **TAB_PANEL_STYLE,
                                                            "display": "flex",
                                                        },
                                                        children=quality_control.layout,
                                                    ),
                                                    html.Div(
                                                        id="tab-panel-anomaly",
                                                        style=TAB_PANEL_STYLE,
                                                        children=anomaly.layout,
                                                    ),
                                                    html.Div(
                                                        id="tab-panel-protein-intensity",
                                                        style=TAB_PANEL_STYLE,
                                                        children=protein_intensity.layout,
                                                    ),
                                                ],
                                            ),
                                        ]
                                    ),
                                ),
                                html.Div(
                                    id="qc-table-div",
                                    className="pqc-table-wrap",
                                    style={"display": "none"},
                                    children=[dt.DataTable(id="qc-table")],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        ),
        html.Div(id="selection-output"),
        html.Div(id="selected-raw-files", style={"display": "none"}),
        html.Div(id="shapley-values", style={"display": "none"}),
        dcc.Store(id="anomaly-predictions", data=None),
        html.Div(id="anomaly-cache-key", style={"display": "none"}),
        dcc.Store(id="anomaly-proposed-flags", data=None),
        dcc.Store(id="anomaly-apply-refresh", data=None),
        html.Div(
            [
                dcc.Dropdown(
                    id="qc-table-columns",
                    multi=True,
                    options=list_to_dropdown_options(C.qc_columns_options),
                    value=C.qc_columns_default,
                ),
                html.Button("Apply", id="qc-update-table"),
                html.Button("Clear Selection", id="qc-clear-selection"),
                html.Button("Remove Unselected", id="qc-remove-unselected"),
                html.Button("Use Downstream", id="accept"),
                html.Button("Prevent Downstream", id="reject"),
                html.Div(id="accept-reject-output"),
            ],
            style={"display": "none"},
        ),
    ],
    className="pqc-dashboard-root",
)

app.layout = layout

anomaly.callbacks(app)
quality_control.callbacks(app)
protein_intensity.callbacks(app)


@app.callback(
    Output("tab-panel-quality-control", "style"),
    Output("tab-panel-anomaly", "style"),
    Output("tab-panel-protein-intensity", "style"),
    Input("tabs", "value"),
)
def render_content(tab):
    qc_style = dict(TAB_PANEL_STYLE)
    anomaly_style = dict(TAB_PANEL_STYLE)
    protein_style = dict(TAB_PANEL_STYLE)

    if tab == "protein_intensity":
        protein_style["display"] = "flex"
    elif tab == "anomaly":
        anomaly_style["display"] = "flex"
    else:
        qc_style["display"] = "flex"

    return qc_style, anomaly_style, protein_style


@app.callback(Output("project", "options"), [Input("B_update", "n_clicks")])
def populate_projects(_n_clicks, **kwargs):
    user = kwargs.get("user")
    result = T.get_projects(user=user)
    return T.dashboard_result_data(result, [])


@app.callback(
    Output("project", "value"),
    Input("project", "options"),
    State("project", "value"),
)
def pick_default_project(options, current_value):
    if not options:
        return None
    valid_values = [o["value"] for o in options]
    if current_value in valid_values:
        return current_value
    return valid_values[0]


@app.callback(Output("pipeline", "options"), [Input("project", "value")])
def populate_pipelines(project, **kwargs):
    user = kwargs.get("user")
    _json = T.dashboard_result_data(T.get_pipelines(project, user=user), [])
    if len(_json) == 0:
        return []
    else:
        output = [{"label": i["name"], "value": i["slug"]} for i in _json]
        return output


@app.callback(
    Output("pipeline", "value"),
    Input("pipeline", "options"),
    State("pipeline", "value"),
)
def pick_default_pipeline(options, current_value):
    if not options:
        return None
    valid_values = [o["value"] for o in options]
    if current_value in valid_values:
        return current_value
    return valid_values[0]


@app.callback(
    Output("qc-admin-session", "data"),
    Output("qc-user-uid", "data"),
    Input("B_update", "n_clicks"),
    State("qc-admin-session", "data"),
    State("qc-user-uid", "data"),
)
def resolve_admin_session(_n_clicks, current_admin_value, current_uid_value, **kwargs):
    user = kwargs.get("user")
    if user is None:
        return False, current_uid_value
    resolved_admin = bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
    resolved_uid = getattr(user, "uuid", None)
    return (
        resolved_admin,
        resolved_uid,
    )


@app.callback(
    Output("scope-uploader", "value"),
    Input("scope-uploader", "options"),
    State("scope-uploader", "value"),
)
def sync_scope_uploader_value(options, current_value):
    values = {
        opt.get("value")
        for opt in list(options or [])
        if isinstance(opt, dict) and opt.get("value") is not None
    }
    if current_value in values:
        raise PreventUpdate
    if "__all__" in values:
        if current_value == "__all__":
            raise PreventUpdate
        return "__all__"
    if current_value is None:
        raise PreventUpdate
    return None

@app.callback(
    Output("qc-table-div", "children"),
    Output("qc-scope-data", "data"),
    Output("qc-uploader-options", "data"),
    Output("pqc-scope-user-field", "style"),
    Output("scope-uploader", "options"),
    Output("qc-loading-probe", "children"),
    Output("pqc-dashboard-alert", "children"),
    Input("project", "value"),
    Input("pipeline", "value"),
    Input("scope-uploader", "value"),
    Input("anomaly-apply-refresh", "data"),
    State("qc-table-columns", "value"),
    State("qc-admin-session", "data"),
    State("qc-user-uid", "data"),
)
def refresh_qc_table(
    project,
    pipeline,
    uploader_filter,
    _anomaly_refresh,
    optional_columns,
    admin_data,
    uid,
    **kwargs,
):
    refresh_probe = str(pd.Timestamp.utcnow().value)
    user = kwargs.get("user")
    effective_uid = getattr(user, "uuid", None) or uid
    is_admin_session = bool(admin_data)
    if user is not None:
        is_admin_session = bool(
            getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
        )

    if (project is None) or (pipeline is None):
        empty_options = [{"label": "All users", "value": "__all__"}]
        scope_style = {"display": "block"} if is_admin_session else {"display": "none"}
        return (
            T.table_from_dataframe(pd.DataFrame(), id="qc-table", row_selectable="multi"),
            {"rows": [], "error": None, "status": "no_data"},
            empty_options,
            scope_style,
            empty_options,
            refresh_probe,
            None,
        )
    optional_columns = optional_columns or C.qc_columns_default
    data_result = T.get_qc_data(
        project=project,
        pipeline=pipeline,
        columns=None,
        data_range=None,
        user=user,
    )
    data = T.dashboard_result_data(data_result, {})
    scope_error = data_result.get("error") if isinstance(data_result, dict) else None
    alert = None
    if scope_error:
        alert = dbc.Alert(
            [
                html.Strong(scope_error.get("message", "Dashboard data error")),
                html.Div(scope_error.get("detail", "")),
            ],
            color="danger",
            className="pqc-dashboard-alert",
        )

    if data is None:
        data = {}
    if isinstance(data, dict):
        max_len = 0
        for value in data.values():
            if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
                max_len = max(max_len, len(value))
        normalized = {}
        for key, value in data.items():
            if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
                arr = list(value)
                if len(arr) < max_len:
                    arr = arr + [None] * (max_len - len(arr))
                elif len(arr) > max_len:
                    arr = arr[:max_len]
                normalized[key] = arr
            else:
                normalized[key] = [None] * max_len
        data = normalized

    df = pd.DataFrame(data)

    if df.empty:
        empty_options = [{"label": "All users", "value": "__all__"}]
        scope_style = {"display": "block"} if is_admin_session else {"display": "none"}
        return (
            T.table_from_dataframe(df, id="qc-table", row_selectable="multi"),
            {"rows": [], "error": scope_error, "status": data_result.get("status", "no_data")},
            empty_options,
            scope_style,
            empty_options,
            refresh_probe,
            alert,
        )

    tmt_missing_cols = _detected_tmt_qc_columns(df.columns)
    selected_optional_cols = list(optional_columns or C.qc_columns_default)
    for tmt_col in tmt_missing_cols:
        if tmt_col not in selected_optional_cols:
            selected_optional_cols.append(tmt_col)
    columns = C.qc_columns_always + selected_optional_cols

    # keep only columns that exist to avoid key errors
    available_cols = [c for c in columns if c in df.columns]

    if "DateAcquired" in df.columns:
        df["DateAcquired"] = pd.to_datetime(df["DateAcquired"], errors="coerce")
    df = df.replace("not detected", np.nan)
    df = _with_sample_labels(df)

    uploader_options = [{"label": "All users", "value": "__all__"}]
    seen_uploader_values = {"__all__"}

    def _add_uploader_option(label, value):
        label = str(label).strip()
        value = str(value).strip()
        if not label or not value:
            return
        if value.lower() in {"nan", "none"}:
            return
        if value in seen_uploader_values:
            return
        seen_uploader_values.add(value)
        uploader_options.append({"label": label, "value": value})

    db_uploader_by_raw = {}
    try:
        from maxquant.models import RawFile as RawFileModel
        from user.models import User as UserModel

        dashboard_user = user
        if dashboard_user is None and effective_uid:
            dashboard_user = UserModel.objects.filter(uuid=effective_uid).first()
        dashboard_is_admin = bool(
            dashboard_user
            and (
                getattr(dashboard_user, "is_staff", False)
                or getattr(dashboard_user, "is_superuser", False)
            )
        )
        allow_all_uploaders = bool(is_admin_session or dashboard_is_admin)

        queryset = RawFileModel.objects.filter(
            pipeline__project__slug=project,
            pipeline__slug=pipeline,
        ).select_related("created_by")
        if not allow_all_uploaders and dashboard_user is None:
            queryset = queryset.none()
        elif (dashboard_user is not None) and (not allow_all_uploaders):
            queryset = queryset.filter(created_by_id=dashboard_user.id)

        rows = (
            queryset.values("orig_file", "created_by__email")
            .distinct()
            .order_by("created_by__email")
        )
        row_count = 0
        for row in rows:
            row_count += 1
            email = (row.get("created_by__email") or "").strip()
            _add_uploader_option(email, email)
            raw_name = str(row.get("orig_file") or "").strip()
            if raw_name and email:
                db_uploader_by_raw[P(raw_name).stem.lower()] = email
    except Exception as exc:
        logging.warning(f"Uploader option DB source failed: {exc}")

    if "Uploader" not in df.columns:
        df["Uploader"] = None
    if ("RawFile" in df.columns) and db_uploader_by_raw:
        mapped_uploaders = df["RawFile"].map(
            lambda raw: db_uploader_by_raw.get(P(str(raw)).stem.lower()) if pd.notna(raw) else None
        )
        df["Uploader"] = df["Uploader"].where(
            df["Uploader"].notna() & (df["Uploader"].astype(str).str.strip() != ""),
            mapped_uploaders,
        )

    uploader_values = (
        df["Uploader"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    uploader_values = sorted(
        {value for value in uploader_values if value and value.lower() not in {"nan", "none"}},
        key=str.lower,
    )
    for value in uploader_values:
        _add_uploader_option(value, value)

    api_uploaders = T.dashboard_result_data(
        T.get_pipeline_uploaders(
        project=project,
        pipeline=pipeline,
        user=user,
        ),
        [],
    )
    for option in api_uploaders:
        _add_uploader_option(option.get("label", ""), option.get("value", ""))

    if (
        is_admin_session
        and uploader_filter
        and uploader_filter != "__all__"
        and "Uploader" in df.columns
    ):
        df = df[df["Uploader"].astype(str) == str(uploader_filter)].reset_index(drop=True)

    df_display = df[available_cols] if len(available_cols) > 0 else pd.DataFrame(index=df.index)
    hidden_columns = [col for col in ["RunKey", "SampleLabel"] if col in df.columns]
    for col in hidden_columns:
        if col not in df_display.columns:
            df_display[col] = df[col]

    records = df.to_dict("records")
    if not is_admin_session:
        uploader_options = [{"label": "All users", "value": "__all__"}]
    show_scope_user = bool(is_admin_session)
    scope_style = {"display": "block"} if show_scope_user else {"display": "none"}
    return (
        T.table_from_dataframe(
            df_display,
            id="qc-table",
            row_selectable="multi",
            hidden_columns=hidden_columns,
        ),
        {"rows": records, "error": scope_error, "status": data_result.get("status", "ok")},
        uploader_options,
        scope_style,
        uploader_options,
        refresh_probe,
        alert,
    )


@app.callback(
    Output("qc-table-columns", "options"),
    Output("qc-table-columns", "value"),
    Input("qc-scope-data", "data"),
    State("qc-table-columns", "value"),
)
def sync_qc_table_columns(scope_data, current_values):
    base_options = list(C.qc_columns_options)
    if not scope_data:
        values = [v for v in list(current_values or C.qc_columns_default) if v in base_options]
        if not values:
            values = list(C.qc_columns_default)
        return list_to_dropdown_options(base_options), values

    df = pd.DataFrame(T.dashboard_rows(scope_data))
    if df.empty:
        values = [v for v in list(current_values or C.qc_columns_default) if v in base_options]
        if not values:
            values = list(C.qc_columns_default)
        return list_to_dropdown_options(base_options), values

    detected_tmt = _detected_tmt_qc_columns(df.columns)

    dynamic_options = [c for c in base_options if c in df.columns and c not in C.qc_columns_always]
    for col in detected_tmt:
        if col not in dynamic_options:
            dynamic_options.append(col)

    valid_current = [c for c in list(current_values or []) if c in dynamic_options]
    if valid_current:
        return list_to_dropdown_options(dynamic_options), valid_current

    dynamic_defaults = [c for c in C.qc_columns_default if c in dynamic_options]
    for col in detected_tmt:
        if col not in dynamic_defaults:
            dynamic_defaults.append(col)

    return list_to_dropdown_options(dynamic_options), dynamic_defaults


@app.callback(
    Output("kpi-samples", "children"),
    Output("kpi-tmt-samples", "children"),
    Output("kpi-median-protein-groups", "children"),
    Output("kpi-median-peptides", "children"),
    Output("kpi-median-msms", "children"),
    Output("kpi-median-missed-cleavages", "children"),
    Output("kpi-median-oxidations", "children"),
    Output("kpi-median-mz-delta", "children"),
    Output("pqc-scope-subtitle", "children"),
    Input("qc-scope-data", "data"),
    Input("project", "value"),
    Input("pipeline", "value"),
)
def update_kpis(data, project, pipeline):
    project_label = project or "No project"
    pipeline_label = pipeline or "No pipeline"

    if data is None:
        return (
            "0",
            "0",
            "--",
            "--",
            "--",
            "--",
            "--",
            "--",
            f"0 runs in {project_label} / {pipeline_label}",
        )
    df = pd.DataFrame(T.dashboard_rows(data))
    if df.empty:
        return (
            "0",
            "0",
            "--",
            "--",
            "--",
            "--",
            "--",
            "--",
            f"0 runs in {project_label} / {pipeline_label}",
        )

    def _tmt_sample_count(frame):
        tmt_channel_map = {}
        for column in frame.columns:
            if not isinstance(column, str):
                continue
            match = re.match(
                r"^TMT(\d+)_(missing_values|peptide_count|protein_group_count)$",
                column,
            )
            if match is None:
                continue
            channel_no = int(match.group(1))
            tmt_channel_map.setdefault(channel_no, []).append(column)

        if tmt_channel_map:
            total = 0
            for _, row in frame.iterrows():
                row_channels = 0
                for channel_cols in tmt_channel_map.values():
                    present = False
                    for column in channel_cols:
                        value = row.get(column)
                        if pd.notna(value):
                            present = True
                            break
                    if present:
                        row_channels += 1
                total += row_channels
            return int(total)

        return 0

    def _run_count(frame):
        for column in ("RunKey", "SampleLabel", "RawFile"):
            if column in frame.columns:
                values = (
                    frame[column]
                    .dropna()
                    .astype(str)
                    .str.strip()
                )
                values = values[
                    (values != "")
                    & (~values.str.lower().isin({"nan", "none"}))
                ]
                if not values.empty:
                    return int(values.nunique())
        return int(len(frame.index))

    def _median(column, unit=""):
        if column not in df.columns:
            return "--"
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().sum() == 0:
            return "--"
        precision = 0 if is_integer_metric_name(column) else metric_display_precision(column, default=1)
        value = f"{series.median():.{precision}f}"
        return f"{value}{unit}" if unit else value

    run_count = _run_count(df)
    tmt_sample_count = _tmt_sample_count(df)
    run_label = "run" if run_count == 1 else "runs"

    return (
        str(run_count),
        str(tmt_sample_count),
        _median("N_protein_groups"),
        _median("N_peptides"),
        _median("MS/MS Identified [%]", "%"),
        _median("N_missed_cleavages_eq_1 [%]", "%"),
        _median("Oxidations [%]", "%"),
        _median("Uncalibrated - Calibrated m/z [ppm] (ave)", "ppm"),
        f"{run_count} {run_label} in {project_label} / {pipeline_label}",
    )


@app.callback(
    Output("qc-table", "selected_rows"),
    Input("qc-clear-selection", "n_clicks"),
    Input("qc-remove-unselected", "n_clicks"),
    Input("qc-figure", "selectedData"),
    Input("qc-figure", "clickData"),
    Input("qc-update-table", "n_clicks"),
    State("qc-table", "selected_rows"),
    State("qc-table", "derived_virtual_indices"),
)
def update_table_selection(
    clear,
    remove_unselected,
    selectedData,
    clickData,
    table_refresh,
    selected_rows,
    virtual_ndxs,
):
    selected_rows = list(selected_rows or [])
    virtual_ndxs = list(virtual_ndxs or [])

    def _point_to_row(point):
        # Prefer explicit row mapping provided by traces (works for heatmaps/expanded views).
        custom = point.get("customdata")
        if isinstance(custom, (int, float)) and int(custom) == custom:
            row_pos = int(custom)
            if 0 <= row_pos < len(virtual_ndxs):
                return virtual_ndxs[row_pos]
            return None

        point_index = point.get("pointIndex")
        if isinstance(point_index, (int, float)) and int(point_index) == point_index:
            point_index = int(point_index)
            if 0 <= point_index < len(virtual_ndxs):
                return virtual_ndxs[point_index]
        return None

    def _extend_rows_from_points(points):
        rows = []
        for point in list(points or []):
            row = _point_to_row(point)
            if row is not None:
                rows.append(row)
        return rows

    # Workaround a bug, this callback is triggered without trigger
    if len(dash.callback_context.triggered) == 0:
        raise PreventUpdate

    changed_id = [p["prop_id"] for p in dash.callback_context.triggered][0]

    if changed_id == "qc-clear-selection.n_clicks":
        return []
    if changed_id == "qc-remove-unselected.n_clicks":
        return []

    if (
        (selectedData is None)
        and (clickData is None)
    ):
        raise PreventUpdate

    if changed_id == "qc-figure.selectedData":
        points = selectedData["points"]
        ndxs = _extend_rows_from_points(points)
        selected_rows.extend(ndxs)

    if changed_id == "qc-figure.clickData":
        point = clickData["points"][0]
        ndx = _point_to_row(point)
        if ndx is not None:
            if ndx in selected_rows:
                selected_rows.remove(ndx)
            else:
                selected_rows.append(ndx)

    selected_rows = list(dict.fromkeys(selected_rows))

    return selected_rows


@app.callback(
    Output("qc-table", "data"),
    Input("qc-remove-unselected", "n_clicks"),
    State("qc-table", "data"),
    State("qc-table", "selected_rows"),
)
def restrict_to_selection(n_clicks, data, selected):
    if n_clicks is None:
        raise PreventUpdate

    # Workaround a bug, this callback is triggered without trigger
    if len(dash.callback_context.triggered) == 0:
        raise PreventUpdate

    df = pd.DataFrame(data)
    df["DateAcquired"] = pd.to_datetime(df["DateAcquired"])
    df = df.reindex(selected)
    return df.to_dict("records")


@app.callback(
    Output("selected-raw-files", "children"),
    Input("qc-table", "selected_rows"),
)
def update_selected_raw_files_1(selected_rows):
    return selected_rows


@app.callback(
    Output("accept-reject-output", "children"),
    Input("accept", "n_clicks"),
    Input("reject", "n_clicks"),
    State("selected-raw-files", "children"),
    State("qc-table", "data"),
    State("project", "value"),
    State("pipeline", "value"),
)
def update_selected_raw_files(
    accept, reject, selection, data, project, pipeline, **kwargs
):
    if ((accept is None) and (reject is None)) or (not selection):
        raise PreventUpdate

    user = kwargs.get("user")

    changed_id = [p["prop_id"] for p in dash.callback_context.triggered][0]
    if changed_id == "accept.n_clicks":
        action = "accept"
    if changed_id == "reject.n_clicks":
        action = "reject"

    data = pd.DataFrame(data)

    data = data.iloc[selection]

    if "RunKey" in data.columns:
        selected_runs = data.RunKey.astype(str).tolist()
    else:
        selected_runs = data.RawFile.astype(str).tolist()

    response = T.set_rawfile_action(
        project, pipeline, selected_runs, action, user=user
    )

    if response["status"] == "success":
        return dbc.Alert("Success", color="success")
    return dbc.Alert(response["status"], color="danger")


if __name__ == "__main__":
    app.run_server(debug=True)
