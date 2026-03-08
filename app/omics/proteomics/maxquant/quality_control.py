# Quality control for MaxQuant output
import pandas as pd
import numpy as np
import logging
import re

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

expected_columns = [
    "N_protein_groups",
    "N_protein_true_hits",
    "N_protein_potential_contaminants",
    "N_protein_reverse_seq",
    "Protein_mean_seq_cov [%]",
    "TMT1_missing_values",
    "TMT2_missing_values",
    "TMT3_missing_values",
    "TMT4_missing_values",
    "TMT5_missing_values",
    "TMT6_missing_values",
    "TMT7_missing_values",
    "TMT8_missing_values",
    "TMT9_missing_values",
    "TMT10_missing_values",
    "TMT11_missing_values",
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
    "Mean_parent_int_frac",
    "Uncalibrated - Calibrated m/z [ppm] (ave)",
    "Uncalibrated - Calibrated m/z [ppm] (sd)",
    "Uncalibrated - Calibrated m/z [Da] (ave)",
    "Uncalibrated - Calibrated m/z [Da] (sd)",
    "Peak Width(ave)",
    "Peak Width (std)",
    "qc1_peptide_charges",
    "N_qc1_missing_values",
    "reporter_intensity_corrected_qc1_ave",
    "reporter_intensity_corrected_qc1_sd",
    "reporter_intensity_corrected_qc1_cv",
    "calibrated_retention_time_qc1",
    "retention_length_qc1",
    "N_of_scans_qc1",
    "qc2_peptide_charges",
    "N_qc2_missing_values",
    "reporter_intensity_corrected_qc2_ave",
    "reporter_intensity_corrected_qc2_sd",
    "reporter_intensity_corrected_qc2_cv",
    "calibrated_retention_time_qc2",
    "retention_length_qc2",
    "N_of_scans_qc2",
    "N_of_Protein_qc_pepts",
    "N_Protein_qc_missing_values",
    "reporter_intensity_corrected_Protein_qc_ave",
    "reporter_intensity_corrected_Protein_qc_sd",
    "reporter_intensity_corrected_Protein_qc_cv",
]


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
    else:
        df = maxquant_qc(txt_path)
        if df is None:
            logging.warning(f"maxquant_qc_csv(): No data generated from {txt_path}")
            return None
        if out_fn is not None:
            df.to_csv(abs_path, index=False)
    df = df.rename(columns=summary_columns_v2_to_v1)

    ordered_columns = list(expected_columns)
    if "Date" in df.columns:
        ordered_columns = ["Date"] + ordered_columns
    if any(col in df.columns for col in summary_columns_v1):
        ordered_columns = [col for col in ["Date"] + summary_columns_v1 + expected_columns]

    existing_columns = [col for col in ordered_columns if col in df.columns]
    remaining_columns = [col for col in df.columns if col not in existing_columns]
    df = df.reindex(columns=existing_columns + remaining_columns)
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

    if "MS/MS Submitted" in df.columns:
        df = df.reindex(columns=["Date"] + summary_columns_v1 + expected_columns)
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

    df1 = df[
        _safe_filter_not_equal(df, "Potential contaminant", "+")
        & _safe_filter_not_equal(df, "Reverse", "+")
        & _safe_filter_not_equal(df, "Majority protein IDs", "QC1|Peptide1")
        & _safe_filter_not_equal(df, "Majority protein IDs", "QC2|Peptide2")
        & _safe_filter_not_equal(df, "Only identified by site", "+")
    ]

    reporter_cols = _reporter_intensity_columns(df1)
    m_v = _missing_counts_by_channel(df1, reporter_cols)

    result = {
        "N_protein_groups": len(df),
        "N_protein_true_hits": n_true_hits,
        "N_protein_potential_contaminants": n_contaminants,
        "N_protein_reverse_seq": n_reverse,
        "Protein_mean_seq_cov [%]": mean_sequence_coverage,
    }

    if len(m_v) != 0:
        l_1 = [
            "TMT1_missing_values",
            "TMT2_missing_values",
            "TMT3_missing_values",
            "TMT4_missing_values",
            "TMT5_missing_values",
            "TMT6_missing_values",
            "TMT7_missing_values",
            "TMT8_missing_values",
            "TMT9_missing_values",
            "TMT10_missing_values",
            "TMT11_missing_values",
        ]
        l_2 = m_v + (11 - len(m_v)) * ["not detected"]
        dic_m_v = dict(zip(l_1, l_2))
        result.update(dic_m_v)

    if protein is None:
        protein = [
            "QC3_BSA"
        ]  # name must be unique, otherwise generates a df with more than one row and ends up in error

    df_qc3 = df[_safe_string_contains(df, "Protein IDs", protein[0])]
    df_qc3 = _select_max_intensity_row(df_qc3)

    if not df_qc3.empty:
        reporter_cols_qc3 = _reporter_intensity_columns(df_qc3)
        ave, std, cv = _row_reporter_stats(
            df_qc3, reporter_cols_qc3, cv_when_mean_zero=None
        )

        dict_info_qc3 = {
            "Protein_qc": protein[0],
            "N_of_Protein_qc_pepts": _safe_column_as_str(df_qc3, "Peptide counts (all)"),
            "N_Protein_qc_missing_values": _missing_counts_as_str(
                df_qc3, reporter_cols_qc3
            ),
            "reporter_intensity_corrected_Protein_qc_ave": ave,
            "reporter_intensity_corrected_Protein_qc_sd": std,
            "reporter_intensity_corrected_Protein_qc_cv": cv,
        }

        result.update(dict_info_qc3)

    else:
        dict_info_qc3 = {
            "Protein_qc": "not detected",
            "N_of_Protein_qc_pepts": "not detected",
            "N_Protein_qc_missing_values": "not detected",
            "reporter_intensity_corrected_Protein_qc_ave": "not detected",
            "reporter_intensity_corrected_Protein_qc_sd": "not detected",
            "reporter_intensity_corrected_Protein_qc_cv": "not detected",
        }
        result.update(dict_info_qc3)

    return pd.Series(result)


def maxquant_qc_peptides(txt_path):
    filename = "peptides.txt"
    df = _read_txt_table(txt_path, filename)
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
    return pd.Series(result).round(2)


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

    if pept_list is None:
        pept_list = [
            "HVLTSIGEK",
            "LTILEELR",
            "ATEEQLK",
            "AEFVEVTK",
            "QTALVELLK",
            "TVMENFVAFVDK",
        ]
    elif len(pept_list) < 6:
        pept_list = pept_list + (6 - len(pept_list)) * ["dummy_peptide"]
    elif len(pept_list) > 6:
        pept_list = pept_list[:6]

    for idx, peptide in enumerate(pept_list, start=1):
        if "Sequence" in df.columns:
            df_pept = df[df["Sequence"] == peptide]
        else:
            df_pept = pd.DataFrame()
        if not df_pept.empty:
            charges = _safe_column_as_str(df_pept, "Charge")
            df_pept = _select_max_intensity_row(df_pept)
            if df_pept.empty:
                dict_info_qc = {
                    f"qc{idx}_peptide_charges": "not detected",
                    f"N_qc{idx}_missing_values": "not detected",
                    f"reporter_intensity_corrected_qc{idx}_ave": "not detected",
                    f"reporter_intensity_corrected_qc{idx}_sd": "not detected",
                    f"reporter_intensity_corrected_qc{idx}_cv": "not detected",
                    f"calibrated_retention_time_qc{idx}": "not detected",
                    f"retention_length_qc{idx}": "not detected",
                    f"N_of_scans_qc{idx}": "not detected",
                }
                result.update(dict_info_qc)
                continue

            reporter_cols = _reporter_intensity_columns(df_pept)
            ave, std, cv = _row_reporter_stats(
                df_pept, reporter_cols, cv_when_mean_zero="not calculated"
            )

            dict_info_qc = {
                f"qc{idx}_peptide": peptide,
                f"qc{idx}_peptide_charges": charges,
                f"N_qc{idx}_missing_values": _missing_counts_as_str(
                    df_pept, reporter_cols
                ),
                f"reporter_intensity_corrected_qc{idx}_ave": ave,
                f"reporter_intensity_corrected_qc{idx}_sd": std,
                f"reporter_intensity_corrected_qc{idx}_cv": cv,
                f"calibrated_retention_time_qc{idx}": _safe_numeric_stat(
                    df_pept, "Calibrated retention time", lambda s: float(s.iloc[0])
                ),
                f"retention_length_qc{idx}": _safe_numeric_stat(
                    df_pept, "Retention length", lambda s: float(s.iloc[0])
                ),
                f"N_of_scans_qc{idx}": _safe_numeric_stat(
                    df_pept, "Number of scans", lambda s: float(s.iloc[0])
                ),
            }

            result.update(dict_info_qc)
        else:
            dict_info_qc = {
                f"qc{idx}_peptide_charges": "not detected",
                f"N_qc{idx}_missing_values": "not detected",
                f"reporter_intensity_corrected_qc{idx}_ave": "not detected",
                f"reporter_intensity_corrected_qc{idx}_sd": "not detected",
                f"reporter_intensity_corrected_qc{idx}_cv": "not detected",
                f"calibrated_retention_time_qc{idx}": "not detected",
                f"retention_length_qc{idx}": "not detected",
                f"N_of_scans_qc{idx}": "not detected",
            }
            result.update(dict_info_qc)

    return pd.Series(result)
