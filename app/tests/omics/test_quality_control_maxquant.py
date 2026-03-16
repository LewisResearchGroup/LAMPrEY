import pandas as pd
import os
import pytest
import shutil
import numbers

from omics.proteomics.maxquant.quality_control import (
    maxquant_qc,
    maxquant_qc_csv,
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

    def test__maxquant_qc_protein_group_id_metrics(self):
        out = maxquant_qc_protein_groups(PATH, protein=None)

        assert out["Protein_score_median"] == pytest.approx(24.15, abs=0.01)
        assert out["Protein_score_mean"] == pytest.approx(43.99, abs=0.01)
        assert out["Protein_qvalue_median"] == pytest.approx(0.0, abs=1e-6)
        assert out["Protein_qvalue_lt_0_01 [%]"] == pytest.approx(100.0, abs=0.01)
        assert out["Protein_unique_peptides_eq_1 [%]"] == pytest.approx(28.81, abs=0.01)
        assert out["Protein_unique_seq_cov_median [%]"] == pytest.approx(13.2, abs=0.01)
        assert isinstance(out["Protein_peptides_median"], numbers.Integral)
        assert isinstance(out["Protein_unique_peptides_median"], numbers.Integral)
        assert isinstance(out["Protein_razor_unique_peptides_median"], numbers.Integral)
        assert isinstance(out["Protein_msms_count_median"], numbers.Integral)

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
            "Peptide_score_median",
            "Peptide_score_mean",
            "Peptide_PEP_median",
            "Peptide_PEP_lt_0_01 [%]",
            "Peptide_length_median",
            "Peptide_msms_count_median",
            "Peptide_unique_groups [%]",
            "Peptide_unique_proteins [%]",
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

    def test__maxquant_qc_peptide_id_metrics(self):
        out = maxquant_qc_peptides(PATH)

        assert out["Peptide_score_median"] == pytest.approx(127.92, abs=0.01)
        assert out["Peptide_score_mean"] == pytest.approx(132.5, abs=0.01)
        assert out["Peptide_PEP_median"] == pytest.approx(0.00008, abs=1e-6)
        assert out["Peptide_PEP_lt_0_01 [%]"] == pytest.approx(88.43, abs=0.01)
        assert out["Peptide_length_median"] == 11
        assert out["Peptide_unique_groups [%]"] == pytest.approx(91.85, abs=0.01)
        assert out["Peptide_unique_proteins [%]"] == pytest.approx(70.83, abs=0.01)
        assert isinstance(out["Peptide_length_median"], numbers.Integral)
        assert isinstance(out["Peptide_msms_count_median"], numbers.Integral)

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
            "RUNDIR",
        ]

        assert all(actual_cols == expected_cols), actual_cols

    @pytest.mark.parametrize("channels", [2, 6, 11, 18])
    def test__dynamic_tmt_channel_counts(self, tmp_path, channels):
        _build_protein_groups(tmp_path, channels)

        out = maxquant_qc_protein_groups(tmp_path, protein=None)

        for idx in range(1, channels + 1):
            assert f"TMT{idx}_missing_values" in out.index

    def test__maxquant_qc_csv_regenerates_stale_cache(self, tmp_path):
        shutil.copytree(PATH, tmp_path, dirs_exist_ok=True)
        stale = pd.DataFrame(
            [
                {
                    "MS": 1,
                    "N_protein_groups": 1,
                    "N_peptides": 1,
                }
            ]
        )
        stale.to_csv(tmp_path / "maxquant_quality_control.csv", index=False)

        out = maxquant_qc_csv(tmp_path)

        assert out.loc[0, "Protein_score_median"] == pytest.approx(24.15, abs=0.01)
        assert out.loc[0, "Peptide_length_median"] == 11
        assert isinstance(out.loc[0, "Peptide_length_median"], numbers.Integral)

    def test__discrete_medians_are_reported_as_integers(self, tmp_path):
        _write_tsv(
            tmp_path,
            "proteinGroups.txt",
            [
                {
                    "Potential contaminant": None,
                    "Reverse": None,
                    "Only identified by site": None,
                    "Sequence coverage [%]": 40.0,
                    "Score": 10.0,
                    "Q-value": 0.001,
                    "Peptides": 2,
                    "Unique peptides": 2,
                    "Razor + unique peptides": 2,
                    "MS/MS count": 4,
                    "Unique sequence coverage [%]": 20.0,
                },
                {
                    "Potential contaminant": None,
                    "Reverse": None,
                    "Only identified by site": None,
                    "Sequence coverage [%]": 50.0,
                    "Score": 12.0,
                    "Q-value": 0.002,
                    "Peptides": 3,
                    "Unique peptides": 3,
                    "Razor + unique peptides": 3,
                    "MS/MS count": 5,
                    "Unique sequence coverage [%]": 30.0,
                },
            ],
        )
        _write_tsv(
            tmp_path,
            "peptides.txt",
            [
                {
                    "Potential contaminant": None,
                    "Reverse": None,
                    "Score": 100.0,
                    "PEP": 0.001,
                    "Length": 10,
                    "MS/MS Count": 4,
                    "Unique (Groups)": "yes",
                    "Unique (Proteins)": "yes",
                    "Missed cleavages": 0,
                    "Last amino acid": "K",
                },
                {
                    "Potential contaminant": None,
                    "Reverse": None,
                    "Score": 120.0,
                    "PEP": 0.002,
                    "Length": 11,
                    "MS/MS Count": 5,
                    "Unique (Groups)": "no",
                    "Unique (Proteins)": "no",
                    "Missed cleavages": 1,
                    "Last amino acid": "R",
                },
            ],
        )

        protein_out = maxquant_qc_protein_groups(tmp_path, protein=None)
        peptide_out = maxquant_qc_peptides(tmp_path)

        assert protein_out["Protein_peptides_median"] == 3
        assert protein_out["Protein_unique_peptides_median"] == 3
        assert protein_out["Protein_razor_unique_peptides_median"] == 3
        assert protein_out["Protein_msms_count_median"] == 5
        assert peptide_out["Peptide_length_median"] == 11
        assert peptide_out["Peptide_msms_count_median"] == 5
        assert isinstance(protein_out["Protein_peptides_median"], numbers.Integral)
        assert isinstance(peptide_out["Peptide_length_median"], numbers.Integral)
