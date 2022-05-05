import os
import numpy as np
import selfies as sf
import exmol
from rdkit.Chem import MolFromSmiles as smi2mol
from rdkit.Chem import MolToSmiles as mol2smi
from rdkit import RDPaths


def test_version():
    assert exmol.__version__


def test_example():
    e = exmol.Example("CC", "", 0, 0, 0, is_origin=True)
    print(e)


def test_randomize_smiles():
    si = "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC"
    m = smi2mol(si)
    so = exmol.stoned.randomize_smiles(m)
    assert si != so


def test_sanitize_smiles():
    si = "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC"
    result = exmol.stoned.sanitize_smiles(si)
    assert result[1] is not None


# TODO let STONED people write these when they finish their repo
def test_run_stoned():
    result = exmol.run_stoned(
        "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC",
        num_samples=10,
        max_mutations=1,
    )
    # Can get duplicates
    assert len(result[0]) >= 0
    assert abs(len(result[0]) - 10) <= 1

    result = exmol.run_stoned(
        "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC",
        num_samples=12,
        max_mutations=3,
    )
    # Can get duplicates
    assert len(result[0]) >= 0
    assert abs(len(result[0]) - 12) <= 1


def test_run_chemed():
    result = exmol.run_chemed("CCCCO", num_samples=10)
    # Can get duplicates
    assert len(result[0]) >= 0


def test_run_custom():
    # use data pregenerated by STONED
    data = ["c1cccnc1", "C1CCCC1", "C1CCNC1" "CCCCN" "CCCC(=O)N", smi2mol("CCCO")]

    result = exmol.run_custom("CCCCO", data=data)
    # Can get duplicates
    assert len(result[0]) >= 0


def test_run_stones_alphabet():
    result = exmol.run_stoned(
        "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC",
        num_samples=10,
        max_mutations=1,
        alphabet=["[C]", "[O]"],
    )
    # Can get duplicates
    assert len(result[0]) >= 0


def test_sample():
    def model(s, se):
        return int("N" in s)

    explanation = exmol.sample_space("CCCC", model, batched=False)
    # check that no redundants
    assert len(explanation) == len(set([e.smiles for e in explanation]))
    # do it without progress bar
    exmol.sample_space("CCCC", model, batched=False, quiet=True)


def test_sample_f():
    def model(s):
        return int("N" in s)

    # try both SMILES and SELFIES
    exmol.sample_space("CCCC", model, batched=False, use_selfies=True)
    exmol.sample_space("CCCC", model, batched=False, use_selfies=False)


def test_sample_preset():
    def model(s, se):
        return int("N" in s)

    explanation = exmol.sample_space("CCCC", model, preset="narrow", batched=False)
    # check that no redundants
    assert len(explanation) == len(set([e.smiles for e in explanation]))


def test_performance():
    def model(s, se):
        return int("F" in s)

    exps = exmol.sample_space(
        "O=C(NCC1CCCCC1N)C2=CC=CC=C2C3=CC=C(F)C=C3C(=O)NC4CCCCC4", model, batched=False
    )
    assert len(exps) > 2000
    cfs = exmol.cf_explain(exps)
    assert cfs[1].similarity > 0.8


def test_sample_chem():
    def model(s, se):
        return int("N" in s)

    explanation = exmol.sample_space(
        "CCCC", model, preset="chemed", batched=False, num_samples=50
    )
    # check that no redundants
    assert len(explanation) == len(set([e.smiles for e in explanation]))

    # try other keywords
    explanation = exmol.sample_space(
        "CCCC",
        model,
        preset="chemed",
        batched=False,
        num_samples=50,
        method_kwargs={"similarity": 0.2},
    )


def test_sample_custom():
    def model(s, se):
        return int("N" in s)

    data = ["c1cccnc1", "C1CCCC1", "C1CNCNC1" "CCCCN" "CCCC(=O)N", smi2mol("CCCO")]
    explanation = exmol.sample_space(
        "CCCC",
        model,
        preset="custom",
        batched=False,
        data=data,
    )
    # check that no redundants
    assert (
        len(explanation) == len(set([e.smiles for e in explanation])) == len(data) + 1
    )


def test_cf_explain():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.cf_explain(samples, 3)
    assert len(exps) == 4  # +1 for base


def test_rcf_explain():
    def model(s, se):
        return len(s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.rcf_explain(samples)
    assert len(exps) == 5
    exps = exmol.rcf_explain(samples, delta=(None, 1))
    assert len(exps) == 3


def test_plot():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.cf_explain(samples, 3)
    exmol.plot_cf(exps)
    exmol.plot_space(samples, exps)


def test_plot_clusters():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.cf_explain(samples, 3)
    exmol.plot_cf(exps)
    exmol.plot_space(samples, exps, highlight_clusters=True)


def test_empty_plot():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.cf_explain(samples, 3)
    exmol.plot_space(samples, [])


def test_compare_img():
    smi1 = "CCCC"
    smi2 = "CCN"
    m1 = smi2mol(smi1)
    m2 = smi2mol(smi2)
    r, _ = exmol.moldiff(m1, m2)
    assert len(r) > 0


def test_add_descriptors():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exmol.add_descriptors(samples, "Classic")
    assert samples[0].descriptors.descriptors is not None


def test_limed():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exmol.lime_explain(samples, descriptor_type="Classic")
    exmol.lime_explain(samples, descriptor_type="MACCS")
    exmol.lime_explain(samples, descriptor_type="ECFP")
    exmol.lime_explain(samples, descriptor_type="ECFP", beta=True)


def test_corrupt_smiles():
    def model(s, se):
        return int("N" in s)

    badsmi = "C/C=C/C(=O)C1CCC(C=C1C)(C)C"
    explanation = exmol.sample_space(badsmi, model, preset="narrow", batched=False)
    assert ~np.isnan(explanation[0].yhat)
