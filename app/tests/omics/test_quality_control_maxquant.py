import pandas as pd
import os
import pytest

from omics.proteomics.maxquant.quality_control import (
    maxquant_qc,
    maxquant_qc_summary,
    maxquant_qc_protein_groups,
    maxquant_qc_peptides,
    maxquant_qc_msmScans,
    maxquant_qc_evidence,
)

PATH = os.path.join("tests", "omics", "data", "maxquant", "tmt11", "example-0")


def _write_tsv(path, filename, data):
    pd.DataFrame(data).to_csv(os.path.join(path, filename), sep="\t", index=False)


def _build_protein_groups(path, channels):
    row = {
        "Potential contaminant": None,
        "Reverse": None,
        "Majority protein IDs": "P00001",
        "Only identified by site": None,
        "Sequence coverage [%]": 50.0,
        "Protein IDs": "P00001",
        "Intensity": 1000.0,
        "Peptide counts (all)": 5,
    }
    for ch in range(1, channels + 1):
        row[f"Reporter intensity corrected {ch}"] = 0 if ch % 2 == 0 else 1000 + ch
    _write_tsv(path, "proteinGroups.txt", [row])


class TestMaxquantQualityControl:
    def test__maxquant_qc_summary(self):
        out = maxquant_qc_summary(PATH)

        assert isinstance(out, pd.Series), f"It is a {type(out)} not a Series"

        expected_cols = [
            "MS",
            "MS/MS",
            "MS3",
            "MS/MS Submitted",
            "MS/MS Identified",
            "MS/MS Identified [%]",
            "Peptide Sequences Identified",
            "Av. Absolute Mass Deviation [mDa]",
            "Mass Standard Deviation [mDa]",
        ]

        assert len(expected_cols) - len(out.index) == 0, (
            f"New columns {out.index[len(expected_cols):]} in output "
            f"file. Adjust expected_cols variable accordingly"
        )

        assert len(list(set(expected_cols) - set(out.index))) == 0, list(
            set(expected_cols) - set(out.index)
        )

        assert (
            ~out.isnull().values.any()
        ), f"NaN value at {out.index[out.isna().any()].tolist()}"

    def test__maxquant_qc_protein_groups(self):
        out = maxquant_qc_protein_groups(PATH, protein=None)

        assert isinstance(out, pd.Series), f"It is a {type(out)} not a Series"

        actual_ndx = out.index.to_list()

        expected_ndx = [
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
        ]

        assert len(expected_ndx) - len(actual_ndx) == 0, (
            f"New columns {actual_ndx[len(expected_ndx):]} in output "
            f"file. Adjust expected_cols variable accordingly"
        )

        assert len(list(set(expected_ndx) - set(actual_ndx))) == 0, list(
            set(expected_ndx) - set(actual_ndx)
        )

        assert (
            ~out.isnull().values.any()
        ), f"NaN value at {actual_ndx[out.isna().any()].tolist()}"

    def test__maxquant_qc_peptides(self):
        out = maxquant_qc_peptides(PATH)

        assert isinstance(out, pd.Series), f"It is a {type(out)} not a Series"

        expected_cols = [
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
        ]

        assert len(expected_cols) - len(out.index) == 0, (
            f"New columns {out.index[len(expected_cols):]} in output "
            f"file. Adjust expected_cols variable accordingly"
        )

        assert len(list(set(expected_cols) - set(out.index))) == 0, list(
            set(expected_cols) - set(out.index)
        )

        assert (
            ~out.isnull().values.any()
        ), f"NaN value at {out.index[out.isna().any()].tolist()}"

    def test__maxquant_qc_msmScans(self):
        out = maxquant_qc_msmScans(PATH)

        assert isinstance(out, pd.Series), f"It is a {type(out)} not a Series"

        expected_cols = ["Mean_parent_int_frac"]

        assert len(expected_cols) - len(out.index) == 0, (
            f"New columns {out.index[len(expected_cols):]} in output "
            f"file. Adjust expected_cols variable accordingly"
        )

        assert len(list(set(expected_cols) - set(out.index))) == 0, list(
            set(expected_cols) - set(out.index)
        )

        assert (
            ~out.isnull().values.any()
        ), f"NaN value at {out.index[out.isna().any()].tolist()}"

    def test__maxquant_qc_evidence(self):
        out = maxquant_qc_evidence(PATH, pept_list=None)

        assert isinstance(out, pd.Series), f"It is a {type(out)} not a Series"

        actual_ndx = out.index.to_list()

        expected_ndx = [
            "Uncalibrated - Calibrated m/z [ppm] (ave)",
            "Uncalibrated - Calibrated m/z [ppm] (sd)",
            "Uncalibrated - Calibrated m/z [Da] (ave)",
            "Uncalibrated - Calibrated m/z [Da] (sd)",
            "Peak Width(ave)",
            "Peak Width (std)",
        ]

        assert len(expected_ndx) - len(actual_ndx) == 0, (
            f"New columns {actual_ndx[len(expected_ndx):]} in output "
            f"file. Adjust expected_cols variable accordingly"
        )

        assert len(list(set(expected_ndx) - set(actual_ndx))) == 0, list(
            set(expected_ndx) - set(actual_ndx)
        )

        assert (
            ~out.isnull().values.any()
        ), f"NaN value at {out[out.isna()].index.to_list()}"

    def test__maxquant_qc_columns(self):
        result = maxquant_qc(PATH, protein=None, pept_list=None)
        actual_cols = result.columns

        expected_cols = [
            "Date",
            "MS",
            "MS/MS",
            "MS3",
            "MS/MS Submitted",
            "MS/MS Identified",
            "MS/MS Identified [%]",
            "Peptide Sequences Identified",
            "Av. Absolute Mass Deviation [mDa]",
            "Mass Standard Deviation [mDa]",
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
            "RUNDIR",
        ]

        assert all(actual_cols == expected_cols), actual_cols

    @pytest.mark.parametrize("channels", [2, 6, 11, 18])
    def test__dynamic_tmt_channel_counts(self, tmp_path, channels):
        _build_protein_groups(tmp_path, channels)

        out = maxquant_qc_protein_groups(tmp_path, protein=None)

        for idx in range(1, channels + 1):
            assert f"TMT{idx}_missing_values" in out.index
