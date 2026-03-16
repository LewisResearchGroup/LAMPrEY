# Quality control for MaxQuant output
import pandas as pd
import numpy as np
import logging
import re

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path as P
from glob import glob
from os.path import dirname, isdir, isfile, join, abspath

summary_columns_v1 = [
    "MS",
    "MS/MS",
    "MS3",
    "MS/MS Submitted",
    "MS/MS Identified",
    "MS/MS Identified [%]",
    "Peptide Sequences Identified",
    "Av. Absolute Mass Deviation [mDa]",
    "Mass Standard Deviation [mDa]"
]

summary_columns_v2 = [
    "MS",
    "MS/MS",
    "MS3",
    "MS/MS submitted",
    "MS/MS identified",
    "MS/MS identified [%]",
    "Peptide sequences identified",
    "Av. absolute mass deviation [mDa]",
    "Mass standard deviation [mDa]"
]

summary_columns_v2_to_v1 = dict(zip(summary_columns_v2, summary_columns_v1))

expected_columns_pre_tmt = [
    "N_protein_groups",
    "N_protein_true_hits",
    "N_protein_potential_contaminants",
    "N_protein_reverse_seq",
    "Protein_mean_seq_cov [%]",
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
]

expected_columns_post_tmt = [
    "N_peptides",
    "N_peptides_potential_contaminants",
    "N_peptides_reverse",
    "Oxidations [%]",
    "N_missed_cleavages_total",
    "N_missed_cleavages_eq_0 [%]",
    "N_missed_cleavages_eq_1 [%]",
    "N_missed_cleavages_eq_2 [%]",
    "N_missed_cleavages_gt_3 [%]",
    "N_peptides_last_amino_acid_K [%]",
    "N_peptides_last_amino_acid_R [%]",
    "N_peptides_last_amino_acid_other [%]",
    "Peptide_score_median",
    "Peptide_score_mean",
    "Peptide_PEP_median",
    "Peptide_PEP_lt_0_01 [%]",
    "Peptide_length_median",
    "Peptide_msms_count_median",
    "Peptide_unique_groups [%]",
    "Peptide_unique_proteins [%]",
    "Mean_parent_int_frac",
    "Uncalibrated - Calibrated m/z [ppm] (ave)",
    "Uncalibrated - Calibrated m/z [ppm] (sd)",
    "Uncalibrated - Calibrated m/z [Da] (ave)",
    "Uncalibrated - Calibrated m/z [Da] (sd)",
    "Peak Width(ave)",
    "Peak Width (std)",
    # Group-specific QC1/QC2/QC3 metrics are temporarily disabled.
    # "qc1_peptide_charges",
    # "N_qc1_missing_values",
    # "reporter_intensity_corrected_qc1_ave",
    # "reporter_intensity_corrected_qc1_sd",
    # "reporter_intensity_corrected_qc1_cv",
    # "calibrated_retention_time_qc1",
    # "retention_length_qc1",
    # "N_of_scans_qc1",
    # "qc2_peptide_charges",
    # "N_qc2_missing_values",
    # "reporter_intensity_corrected_qc2_ave",
    # "reporter_intensity_corrected_qc2_sd",
    # "reporter_intensity_corrected_qc2_cv",
    # "calibrated_retention_time_qc2",
    # "retention_length_qc2",
    # "N_of_scans_qc2",
    # "N_of_Protein_qc_pepts",
    # "N_Protein_qc_missing_values",
    # "reporter_intensity_corrected_Protein_qc_ave",
    # "reporter_intensity_corrected_Protein_qc_sd",
    # "reporter_intensity_corrected_Protein_qc_cv",
]

INTEGER_METRIC_NAMES = {
    "MS",
    "MS/MS",
    "MS3",
    "MS/MS Submitted",
    "MS/MS submitted",
    "MS/MS Identified",
    "MS/MS identified",
    "Peptide Sequences Identified",
    "Peptide sequences identified",
    "N_protein_groups",
    "N_protein_true_hits",
    "N_protein_potential_contaminants",
    "N_protein_reverse_seq",
    "Protein_peptides_median",
    "Protein_unique_peptides_median",
    "Protein_razor_unique_peptides_median",
    "Protein_msms_count_median",
    "N_peptides",
    "N_peptides_potential_contaminants",
    "N_peptides_reverse",
    "N_missed_cleavages_total",
    "Peptide_length_median",
    "Peptide_msms_count_median",
}

INTEGER_METRIC_PATTERNS = (
    re.compile(r"^TMT\d+_missing_values$"),
)

METRIC_PRECISION_OVERRIDES = {
    "Protein_qvalue_median": 6,
    "Peptide_PEP_median": 6,
}


def is_integer_metric_name(name):
    name = str(name)
    return name in INTEGER_METRIC_NAMES or any(
        pattern.match(name) for pattern in INTEGER_METRIC_PATTERNS
    )


def metric_display_precision(name, default=2):
    return METRIC_PRECISION_OVERRIDES.get(str(name), default)


def _read_txt_table(path, filename, **kwargs):
    table_path = P(path) / P(filename)
    try:
        return pd.read_csv(table_path, sep="\t", **kwargs)
    except FileNotFoundError:
        logging.warning("Missing MaxQuant table: %s", table_path)
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        logging.warning("Empty MaxQuant table: %s", table_path)
        return pd.DataFrame()


def _safe_numeric_stat(df, column, fn):
    if column not in df.columns:
        return np.nan
    series = pd.to_numeric(df[column], errors="coerce")
    return fn(series)


def _safe_eq_plus_count(df, column):
    if column not in df.columns:
        return 0
    return df[column].fillna("-").eq("+").sum()


def _safe_string_contains(df, column, pattern):
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].astype(str).str.contains(pattern, na=False, case=True)


def _safe_filter_not_equal(df, column, value):
    if column not in df.columns:
        return pd.Series(True, index=df.index)
    return df[column].fillna("").ne(value)


def _safe_column_as_str(df, column, default="not detected"):
    if column not in df.columns:
        return default
    return ";".join([str(x) for x in df[column].to_list()])


def _filtered_identifications(df, include_only_identified_by_site=False):
    mask = (
        _safe_filter_not_equal(df, "Potential contaminant", "+")
        & _safe_filter_not_equal(df, "Reverse", "+")
    )
    if not include_only_identified_by_site:
        mask &= _safe_filter_not_equal(df, "Only identified by site", "+")
    return df[mask]


def _safe_numeric_percentage(df, column, predicate):
    if df.empty:
        return 0.0
    if column not in df.columns:
        return np.nan
    series = pd.to_numeric(df[column], errors="coerce")
    valid = series.notna()
    if valid.sum() == 0:
        return np.nan
    return predicate(series[valid]).mean() * 100


def _safe_yes_percentage(df, column):
    if df.empty:
        return 0.0
    if column not in df.columns:
        return np.nan
    series = df[column].astype(str).str.lower()
    return series.eq("yes").mean() * 100


def _round_half_up(value, precision=0):
    quantizer = Decimal("1") if precision == 0 else Decimal(f"1e-{precision}")
    return Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP)


def _integer_median(series):
    valid = series.dropna()
    if valid.empty:
        return np.nan
    return int(_round_half_up(valid.median(skipna=True)))


def _normalize_metric_value(key, value, precision_overrides=None, default_precision=2):
    precision_overrides = precision_overrides or {}
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        if is_integer_metric_name(key):
            return int(_round_half_up(value))
        precision = precision_overrides.get(key, default_precision)
        return round(float(value), precision)
    return value


def _normalize_metric_dataframe(df, precision_overrides=None, default_precision=2):
    precision_overrides = precision_overrides or {}
    normalized = df.copy()
    for column in normalized.columns:
        normalized[column] = normalized[column].map(
            lambda value: _normalize_metric_value(
                column,
                value,
                precision_overrides=precision_overrides,
                default_precision=default_precision,
            )
        )
    return normalized


def _protein_identification_metrics(df):
    if df.empty:
        return {
            "Protein_score_median": 0.0,
            "Protein_score_mean": 0.0,
            "Protein_qvalue_median": 0.0,
            "Protein_qvalue_lt_0_01 [%]": 0.0,
            "Protein_peptides_median": 0,
            "Protein_unique_peptides_median": 0,
            "Protein_razor_unique_peptides_median": 0,
            "Protein_unique_peptides_eq_1 [%]": 0.0,
            "Protein_msms_count_median": 0,
            "Protein_unique_seq_cov_median [%]": 0.0,
        }
    return {
        "Protein_score_median": _safe_numeric_stat(
            df, "Score", lambda s: s.median(skipna=True)
        ),
        "Protein_score_mean": _safe_numeric_stat(
            df, "Score", lambda s: s.mean(skipna=True)
        ),
        "Protein_qvalue_median": _safe_numeric_stat(
            df, "Q-value", lambda s: s.median(skipna=True)
        ),
        "Protein_qvalue_lt_0_01 [%]": _safe_numeric_percentage(
            df, "Q-value", lambda s: s < 0.01
        ),
        "Protein_peptides_median": _safe_numeric_stat(
            df, "Peptides", _integer_median
        ),
        "Protein_unique_peptides_median": _safe_numeric_stat(
            df, "Unique peptides", _integer_median
        ),
        "Protein_razor_unique_peptides_median": _safe_numeric_stat(
            df, "Razor + unique peptides", _integer_median
        ),
        "Protein_unique_peptides_eq_1 [%]": _safe_numeric_percentage(
            df, "Unique peptides", lambda s: s == 1
        ),
        "Protein_msms_count_median": _safe_numeric_stat(
            df, "MS/MS count", _integer_median
        ),
        "Protein_unique_seq_cov_median [%]": _safe_numeric_stat(
            df, "Unique sequence coverage [%]", lambda s: s.median(skipna=True)
        ),
    }


def _peptide_identification_metrics(df):
    if df.empty:
        return {
            "Peptide_score_median": 0.0,
            "Peptide_score_mean": 0.0,
            "Peptide_PEP_median": 0.0,
            "Peptide_PEP_lt_0_01 [%]": 0.0,
            "Peptide_length_median": 0,
            "Peptide_msms_count_median": 0,
            "Peptide_unique_groups [%]": 0.0,
            "Peptide_unique_proteins [%]": 0.0,
        }
    return {
        "Peptide_score_median": _safe_numeric_stat(
            df, "Score", lambda s: s.median(skipna=True)
        ),
        "Peptide_score_mean": _safe_numeric_stat(
            df, "Score", lambda s: s.mean(skipna=True)
        ),
        "Peptide_PEP_median": _safe_numeric_stat(
            df, "PEP", lambda s: s.median(skipna=True)
        ),
        "Peptide_PEP_lt_0_01 [%]": _safe_numeric_percentage(
            df, "PEP", lambda s: s < 0.01
        ),
        "Peptide_length_median": _safe_numeric_stat(
            df, "Length", _integer_median
        ),
        "Peptide_msms_count_median": _safe_numeric_stat(
            df, "MS/MS Count", _integer_median
        ),
        "Peptide_unique_groups [%]": _safe_yes_percentage(df, "Unique (Groups)"),
        "Peptide_unique_proteins [%]": _safe_yes_percentage(df, "Unique (Proteins)"),
    }


def _round_metric_series(result, precision_overrides=None, default_precision=2):
    precision_overrides = precision_overrides or {}
    normalized = {
        key: _normalize_metric_value(
            key,
            value,
            precision_overrides=precision_overrides,
            default_precision=default_precision,
        )
        for key, value in result.items()
    }
    return pd.Series(normalized, dtype=object)


def _missing_counts_by_channel(df, reporter_cols):
    if not reporter_cols:
        return []
    return df[reporter_cols].replace(np.nan, 0).isin([0]).sum().to_list()


def _missing_counts_as_str(df, reporter_cols, default="not detected"):
    if not reporter_cols:
        return default
    return ";".join([str(x) for x in _missing_counts_by_channel(df, reporter_cols)])


def _row_reporter_stats(df, reporter_cols, cv_when_mean_zero=None):
    if df.empty or not reporter_cols:
        return (np.nan, np.nan, cv_when_mean_zero)

    row = pd.to_numeric(df[reporter_cols].iloc[0], errors="coerce")
    ave = float(row.mean(skipna=True))
    std = float(row.std(ddof=0, skipna=True))

    if pd.isna(ave):
        cv = np.nan
    elif ave != 0:
        cv = std / ave * 100
    else:
        cv = cv_when_mean_zero
    return ave, std, cv


def _select_max_intensity_row(df, intensity_col="Intensity"):
    if df.empty:
        return df
    if intensity_col not in df.columns:
        return df.head(1)
    max_intensity = pd.to_numeric(df[intensity_col], errors="coerce").max(skipna=True)
    if pd.isna(max_intensity):
        return df.head(1)
    return df[pd.to_numeric(df[intensity_col], errors="coerce").eq(max_intensity)].head(1)


def _reporter_intensity_columns(df):
    cols = df.filter(regex=r"^Reporter intensity corrected").columns.to_list()
    return sorted(
        cols,
        key=lambda col: int(re.search(r"\b(\d+)\b", str(col)).group(1))
        if re.search(r"\b(\d+)\b", str(col))
        else 10**9,
    )


def _tmt_missing_value_columns(df):
    cols = [
        c
        for c in df.columns
        if isinstance(c, str) and re.match(r"^TMT\d+_missing_values$", c)
    ]
    return sorted(cols, key=lambda c: int(re.search(r"\d+", c).group(0)))


def _ordered_columns(df):
    if "MS/MS Submitted" in df.columns:
        summary_cols = [c for c in summary_columns_v1 if c in df.columns]
    elif "MS/MS submitted" in df.columns:
        summary_cols = [c for c in summary_columns_v2 if c in df.columns]
    else:
        summary_cols = []

    tmt_cols = _tmt_missing_value_columns(df)
    core_cols = ["Date"] + summary_cols + expected_columns_pre_tmt + tmt_cols + expected_columns_post_tmt
    core_cols = list(dict.fromkeys(core_cols))
    extra_cols = [c for c in df.columns if c not in core_cols]
    return core_cols + extra_cols


def _cached_qc_is_stale(df):
    required_cols = set(expected_columns_pre_tmt + expected_columns_post_tmt)
    return not required_cols.issubset(set(df.columns))


def collect_maxquant_qc_data(root_path, force_update=False, from_csvs=True):
    """
    Generate MaxQuant quality control in all
    sub-directories of `root_path` where summary.txt is found.
    """
    paths = [
        abspath(dirname(i)) for i in glob(f"{root_path}/**/summary.txt", recursive=True)
    ]
    if len(paths) == 0:
        return None
    if from_csvs:
        dfs = [maxquant_qc_csv(path, force_update=force_update) for path in paths]
    else:
        dfs = [maxquant_qc(path) for path in paths]
    return pd.concat(dfs, sort=False).reset_index(drop=True)


def maxquant_qc_csv(
    txt_path,
    out_fn="maxquant_quality_control.csv",
    force_update=False,
):
    abs_path = join(txt_path, out_fn)
    if isfile(abs_path) and not force_update:
        df = pd.read_csv(abs_path)
        normalized_df = _normalize_metric_dataframe(
            df,
            precision_overrides=METRIC_PRECISION_OVERRIDES,
        )
        if not normalized_df.equals(df):
            df = normalized_df
            df.to_csv(abs_path, index=False)
        if _cached_qc_is_stale(df):
            logging.info("Regenerating stale MaxQuant QC cache: %s", abs_path)
            df = maxquant_qc(txt_path)
    else:
        df = maxquant_qc(txt_path)
        if df is None:
            logging.warning(f"maxquant_qc_csv(): No data generated from {txt_path}")
            return None
        if out_fn is not None:
            df = _normalize_metric_dataframe(
                df,
                precision_overrides=METRIC_PRECISION_OVERRIDES,
            )
            df.to_csv(abs_path, index=False)
    df = df.rename(columns=summary_columns_v2_to_v1)

    df = df.reindex(columns=_ordered_columns(df))
    return df


def maxquant_qc(txt_path, protein=None, pept_list=None):
    """
    Runs all MaxQuant quality control functions
    and returns a concatenated pandas.Series()
    object including meta data.
    Args:
        txt_path: path with MaxQuant txt output.
        protein: list with protein name (only the first one will be processed). If None then protein = ['BSA']
        pept_list: list with peptides names (only the first six will be processed). If None then
        pept_list = ["HVLTSIGEK", "LTILEELR", "ATEEQLK", "AEFVEVTK", "QTALVELLK", "TVMENFVAFVDK"]
    """
    txt_path = P(abspath(txt_path))
    meta_json = txt_path / P("meta.json")
    assert isdir(txt_path), f"Path does not exists: {txt_path}"
    dfs = []
    if isfile(meta_json):
        meta = pd.read_json(meta_json, typ="series")
        dfs.append(meta)
    for df in [
        maxquant_qc_summary(txt_path),
        maxquant_qc_protein_groups(txt_path, protein),
        maxquant_qc_peptides(txt_path),
        maxquant_qc_msmScans(txt_path),
        maxquant_qc_evidence(txt_path, pept_list),
    ]:
        dfs.append(df)
    if len(dfs) == 0:
        return None
    df = pd.concat(dfs, sort=False).to_frame().T
    df = df.rename(columns=summary_columns_v2_to_v1)
    df["RUNDIR"] = str(txt_path)

    df = _normalize_metric_dataframe(
        df,
        precision_overrides=METRIC_PRECISION_OVERRIDES,
    )
    df = df.reindex(columns=_ordered_columns(df))
    return df.infer_objects()


def maxquant_qc_summary(txt_path):
    filename = "summary.txt"
    df_summary_df = _read_txt_table(txt_path, filename, nrows=1)
    if df_summary_df.empty:
        return pd.Series(dtype=object)
    df_summary = df_summary_df.T[0]

    if "MS/MS Submitted" in df_summary.index:
        return df_summary[summary_columns_v1]
    elif "MS/MS submitted" in df_summary.index:
        return df_summary[summary_columns_v2].rename(index=summary_columns_v2_to_v1)
    return pd.Series(dtype=object)

def maxquant_qc_protein_groups(txt_path, protein=None):
    filename = "proteinGroups.txt"
    df = _read_txt_table(txt_path, filename)
    n_contaminants = _safe_eq_plus_count(df, "Potential contaminant")
    n_reverse = _safe_eq_plus_count(df, "Reverse")
    n_true_hits = len(df) - (n_contaminants + n_reverse)
    if (
        "Potential contaminant" in df.columns
        and "Reverse" in df.columns
        and "Sequence coverage [%]" in df.columns
    ):
        mean_sequence_coverage = df[
            (df["Potential contaminant"].isnull()) & (df["Reverse"].isnull())
        ]["Sequence coverage [%]"].mean(skipna=True)
    else:
        mean_sequence_coverage = np.nan

    df1 = _filtered_identifications(df, include_only_identified_by_site=False)
    # Group-specific QC1/QC2 exclusions are temporarily disabled.
    # df1 = df[
    #     _safe_filter_not_equal(df, "Potential contaminant", "+")
    #     & _safe_filter_not_equal(df, "Reverse", "+")
    #     & _safe_filter_not_equal(df, "Majority protein IDs", "QC1|Peptide1")
    #     & _safe_filter_not_equal(df, "Majority protein IDs", "QC2|Peptide2")
    #     & _safe_filter_not_equal(df, "Only identified by site", "+")
    # ]

    reporter_cols = _reporter_intensity_columns(df1)
    m_v = _missing_counts_by_channel(df1, reporter_cols)

    result = {
        "N_protein_groups": len(df),
        "N_protein_true_hits": n_true_hits,
        "N_protein_potential_contaminants": n_contaminants,
        "N_protein_reverse_seq": n_reverse,
        "Protein_mean_seq_cov [%]": mean_sequence_coverage,
    }
    result.update(_protein_identification_metrics(df1))

    if len(m_v) != 0:
        dic_m_v = {f"TMT{i + 1}_missing_values": v for i, v in enumerate(m_v)}
        result.update(dic_m_v)

    # Group-specific QC3_BSA metrics are temporarily disabled.
    # if protein is None:
    #     protein = [
    #         "QC3_BSA"
    #     ]  # name must be unique, otherwise generates a df with more than one row and ends up in error
    #
    # df_qc3 = df[_safe_string_contains(df, "Protein IDs", protein[0])]
    # df_qc3 = _select_max_intensity_row(df_qc3)
    #
    # if not df_qc3.empty:
    #     reporter_cols_qc3 = _reporter_intensity_columns(df_qc3)
    #     ave, std, cv = _row_reporter_stats(
    #         df_qc3, reporter_cols_qc3, cv_when_mean_zero=None
    #     )
    #
    #     dict_info_qc3 = {
    #         "Protein_qc": protein[0],
    #         "N_of_Protein_qc_pepts": _safe_column_as_str(df_qc3, "Peptide counts (all)"),
    #         "N_Protein_qc_missing_values": _missing_counts_as_str(
    #             df_qc3, reporter_cols_qc3
    #         ),
    #         "reporter_intensity_corrected_Protein_qc_ave": ave,
    #         "reporter_intensity_corrected_Protein_qc_sd": std,
    #         "reporter_intensity_corrected_Protein_qc_cv": cv,
    #     }
    #
    #     result.update(dict_info_qc3)
    #
    # else:
    #     dict_info_qc3 = {
    #         "Protein_qc": "not detected",
    #         "N_of_Protein_qc_pepts": "not detected",
    #         "N_Protein_qc_missing_values": "not detected",
    #         "reporter_intensity_corrected_Protein_qc_ave": "not detected",
    #         "reporter_intensity_corrected_Protein_qc_sd": "not detected",
    #         "reporter_intensity_corrected_Protein_qc_cv": "not detected",
    #     }
    #     result.update(dict_info_qc3)

    return _round_metric_series(
        result,
        precision_overrides=METRIC_PRECISION_OVERRIDES,
    )


def maxquant_qc_peptides(txt_path):
    filename = "peptides.txt"
    df = _read_txt_table(txt_path, filename)
    df_identified = _filtered_identifications(df, include_only_identified_by_site=True)
    max_missed_cleavages = 3
    last_amino_acids = ["K", "R"]
    n_peptides = len(df)
    if n_peptides == 0:
        return pd.Series(
            {
                "N_peptides": 0,
                "N_peptides_potential_contaminants": 0,
                "N_peptides_reverse": 0,
                "Oxidations [%]": 0.0,
                "N_missed_cleavages_total": 0,
                "N_missed_cleavages_eq_0 [%]": 0.0,
                "N_missed_cleavages_eq_1 [%]": 0.0,
                "N_missed_cleavages_eq_2 [%]": 0.0,
                "N_missed_cleavages_gt_3 [%]": 0.0,
                "N_peptides_last_amino_acid_K [%]": 0.0,
                "N_peptides_last_amino_acid_R [%]": 0.0,
                "N_peptides_last_amino_acid_other [%]": 0.0,
                "Peptide_score_median": 0.0,
                "Peptide_score_mean": 0.0,
                "Peptide_PEP_median": 0.0,
                "Peptide_PEP_lt_0_01 [%]": 0.0,
                "Peptide_length_median": 0,
                "Peptide_msms_count_median": 0,
                "Peptide_unique_groups [%]": 0.0,
                "Peptide_unique_proteins [%]": 0.0,
            }
        )
    n_contaminants = _safe_eq_plus_count(df, "Potential contaminant")
    n_reverse = _safe_eq_plus_count(df, "Reverse")
    if "Oxidation (M) site IDs" in df.columns:
        ox_pep_seq = len(df) - df["Oxidation (M) site IDs"].isnull().sum()
    else:
        ox_pep_seq = 0
    ox_pep_seq_percent = ox_pep_seq / n_peptides * 100
    missed_cleavages = (
        pd.to_numeric(df["Missed cleavages"], errors="coerce")
        if "Missed cleavages" in df.columns
        else pd.Series([np.nan] * n_peptides)
    )
    last_aa = (
        df["Last amino acid"]
        if "Last amino acid" in df.columns
        else pd.Series([""] * n_peptides)
    )
    result = {
        "N_peptides": n_peptides,
        "N_peptides_potential_contaminants": n_contaminants,
        "N_peptides_reverse": n_reverse,
        "Oxidations [%]": ox_pep_seq_percent,
        "N_missed_cleavages_total": (missed_cleavages != 0).sum(),
    }
    for n in range(max_missed_cleavages):
        result[f"N_missed_cleavages_eq_{n} [%]"] = (
            (missed_cleavages == n).sum() / n_peptides * 100
        )
    result[f"N_missed_cleavages_gt_{max_missed_cleavages} [%]"] = (
        (missed_cleavages > max_missed_cleavages).sum() / n_peptides * 100
    )
    for amino in last_amino_acids:
        result[f"N_peptides_last_amino_acid_{amino} [%]"] = (
            last_aa.eq(amino).sum() / n_peptides * 100
        )
    result["N_peptides_last_amino_acid_other [%]"] = (
        (~last_aa.isin(last_amino_acids)).sum() / n_peptides * 100
    )
    result.update(_peptide_identification_metrics(df_identified))
    return _round_metric_series(
        result,
        precision_overrides=METRIC_PRECISION_OVERRIDES,
    )


def maxquant_qc_msmScans(txt_path, t0=None, tf=None):
    filename = "msmsScans.txt"
    df = _read_txt_table(txt_path, filename)
    if t0 is None and "Retention time" in df.columns:
        t0 = df["Retention time"].min()
    if tf is None and "Retention time" in df.columns:
        tf = df["Retention time"].max()
    mean_parent_int_frac = _safe_numeric_stat(
        df, "Parent intensity fraction", lambda s: s.mean(skipna=True)
    )
    results = {"Mean_parent_int_frac": mean_parent_int_frac}
    return pd.Series(results).round(2)


def maxquant_qc_evidence(txt_path, pept_list=None):
    filename = "evidence.txt"
    df = _read_txt_table(txt_path, filename)

    result = {
        "Uncalibrated - Calibrated m/z [ppm] (ave)": _safe_numeric_stat(
            df, "Uncalibrated - Calibrated m/z [ppm]", lambda s: s.mean(skipna=True)
        ),
        "Uncalibrated - Calibrated m/z [ppm] (sd)": _safe_numeric_stat(
            df,
            "Uncalibrated - Calibrated m/z [ppm]",
            lambda s: s.std(ddof=0, skipna=True),
        ),
        "Uncalibrated - Calibrated m/z [Da] (ave)": _safe_numeric_stat(
            df, "Uncalibrated - Calibrated m/z [Da]", lambda s: s.mean(skipna=True)
        ),
        "Uncalibrated - Calibrated m/z [Da] (sd)": _safe_numeric_stat(
            df,
            "Uncalibrated - Calibrated m/z [Da]",
            lambda s: s.std(ddof=0, skipna=True),
        ),
        "Peak Width(ave)": _safe_numeric_stat(
            df, "Retention length", lambda s: s.mean(skipna=True)
        ),
        "Peak Width (std)": _safe_numeric_stat(
            df, "Retention length", lambda s: s.std(ddof=0, skipna=True)
        ),
    }

    # Group-specific QC1/QC2/QC3 peptide metrics are temporarily disabled.
    # if pept_list is None:
    #     pept_list = [
    #         "HVLTSIGEK",
    #         "LTILEELR",
    #         "ATEEQLK",
    #         "AEFVEVTK",
    #         "QTALVELLK",
    #         "TVMENFVAFVDK",
    #     ]
    # elif len(pept_list) < 6:
    #     pept_list = pept_list + (6 - len(pept_list)) * ["dummy_peptide"]
    # elif len(pept_list) > 6:
    #     pept_list = pept_list[:6]
    #
    # for idx, peptide in enumerate(pept_list, start=1):
    #     if "Sequence" in df.columns:
    #         df_pept = df[df["Sequence"] == peptide]
    #     else:
    #         df_pept = pd.DataFrame()
    #     if not df_pept.empty:
    #         charges = _safe_column_as_str(df_pept, "Charge")
    #         df_pept = _select_max_intensity_row(df_pept)
    #         if df_pept.empty:
    #             dict_info_qc = {
    #                 f"qc{idx}_peptide_charges": "not detected",
    #                 f"N_qc{idx}_missing_values": "not detected",
    #                 f"reporter_intensity_corrected_qc{idx}_ave": "not detected",
    #                 f"reporter_intensity_corrected_qc{idx}_sd": "not detected",
    #                 f"reporter_intensity_corrected_qc{idx}_cv": "not detected",
    #                 f"calibrated_retention_time_qc{idx}": "not detected",
    #                 f"retention_length_qc{idx}": "not detected",
    #                 f"N_of_scans_qc{idx}": "not detected",
    #             }
    #             result.update(dict_info_qc)
    #             continue
    #
    #         reporter_cols = _reporter_intensity_columns(df_pept)
    #         ave, std, cv = _row_reporter_stats(
    #             df_pept, reporter_cols, cv_when_mean_zero="not calculated"
    #         )
    #
    #         dict_info_qc = {
    #             f"qc{idx}_peptide": peptide,
    #             f"qc{idx}_peptide_charges": charges,
    #             f"N_qc{idx}_missing_values": _missing_counts_as_str(
    #                 df_pept, reporter_cols
    #             ),
    #             f"reporter_intensity_corrected_qc{idx}_ave": ave,
    #             f"reporter_intensity_corrected_qc{idx}_sd": std,
    #             f"reporter_intensity_corrected_qc{idx}_cv": cv,
    #             f"calibrated_retention_time_qc{idx}": _safe_numeric_stat(
    #                 df_pept, "Calibrated retention time", lambda s: float(s.iloc[0])
    #             ),
    #             f"retention_length_qc{idx}": _safe_numeric_stat(
    #                 df_pept, "Retention length", lambda s: float(s.iloc[0])
    #             ),
    #             f"N_of_scans_qc{idx}": _safe_numeric_stat(
    #                 df_pept, "Number of scans", lambda s: float(s.iloc[0])
    #             ),
    #         }
    #
    #         result.update(dict_info_qc)
    #     else:
    #         dict_info_qc = {
    #             f"qc{idx}_peptide_charges": "not detected",
    #             f"N_qc{idx}_missing_values": "not detected",
    #             f"reporter_intensity_corrected_qc{idx}_ave": "not detected",
    #             f"reporter_intensity_corrected_qc{idx}_sd": "not detected",
    #             f"reporter_intensity_corrected_qc{idx}_cv": "not detected",
    #             f"calibrated_retention_time_qc{idx}": "not detected",
    #             f"retention_length_qc{idx}": "not detected",
    #             f"N_of_scans_qc{idx}": "not detected",
    #         }
    #         result.update(dict_info_qc)

    return pd.Series(result)
