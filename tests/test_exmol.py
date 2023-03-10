import os
import numpy as np
from exmol.exmol import lime_explain
import selfies as sf
import exmol
from rdkit.Chem import MolFromSmiles as smi2mol
from rdkit.Chem import MolToSmiles as mol2smi
from rdkit import RDPaths
from rdkit.Chem import AllChem
import random


def test_version():
    assert exmol.__version__


def test_synspace_anybonds():
    def rand_model(smi):
        return random.randint(0, 1)

    palbo_smi = "CC(=O)C1=C(C)c2cnc(Nc3ccc(cn3)N4CCNCC4)nc2N(C5CCCC5)C1=O"
    exmol.sample_space(palbo_smi, rand_model, batched=False, preset="synspace")


def test_example():
    e = exmol.Example("CC", "", 0, 0, 0, is_origin=True)


def test_randomize_smiles():
    si = "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC"
    m = smi2mol(si)
    so = exmol.stoned.randomize_smiles(m)
    assert si != so


def test_sanitize_smiles():
    si = "N#CC=CC(C(=O)NCC1=CC=CC=C1C(=O)N)(C)CC2=CC=C(F)C=C2CC"
    result = exmol.stoned.sanitize_smiles(si)
    assert result[2]


def test_sanitize_smiles_chiral():
    si = "CC1=CC[C@@H](CC1)C(=C)C"
    result = exmol.stoned.sanitize_smiles(si)
    assert "@" in result[1]


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


def test_kekulize_bug():
    problem_alphabet = {
        "[#Branch1]",
        "[#Branch2]",
        "[#C]",
        "[#N]",
        "[-/Ring1]",
        "[/C]",
        "[/N]",
        "[=Branch1]",
        "[=Branch2]",
        "[=C]",
        "[=Cd]",
        "[=Co]",
        "[=Cr]",
        "[=Fe]",
        "[=Mn]",
        "[=Mo]",
        "[=N+1]",
        "[=N]",
        "[=O+1]",
        "[=O]",
        "[=P]",
        "[=Pb]",
        "[=Ring1]",
        "[=S]",
        "[=Se]",
        "[=Zn]",
        "[B]",
        "[Ba+2]",
        "[Bi+3]",
        "[Br-1]",
        "[Br]",
        "[Branch1]",
        "[Branch2]",
        "[C+1]",
        "[C@@H1]",
        "[C@@]",
        "[C@H1]",
        "[C@]",
        "[C]",
        "[Ca+2]",
        "[Cd+2]",
        "[Cl-1]",
        "[ClH0]",
        "[Cl]",
        "[Co+2]",
        "[Cr+3]",
        "[Cr]",
        "[Cu+2]",
        "[Cu]",
        "[F-1]",
        "[F]",
        "[Fe]",
        "[H+1]",
        "[H-1]",
        "[Hg+1]",
        "[Hg]",
        "[I-1]",
        "[I]",
        "[K+1]",
        "[La]",
        "[Li+1]",
        "[Lu+3]",
        "[Mg+2]",
        "[Mn+2]",
        "[Mn+3]",
        "[Mn]",
        "[Mo]",
        "[N+1]",
        "[N-1]",
        "[NH1+1]",
        "[NH1]",
        "[NH4+1]",
        "[N]",
        "[Na+1]",
        "[Na]",
        "[O-1]",
        "[O-2]",
        "[O]",
        "[P+1]",
        "[P]",
        "[Pb]",
        "[Re]",
        "[Ring1]",
        "[Ring2]",
        "[S-1]",
        "[S]",
        "[Sb]",
        "[Se]",
        "[SiH1]",
        "[Si]",
        "[Sn]",
        "[Sr+2]",
        "[V]",
        "[Y+3]",
        "[Zn+2]",
        "[Zn]",
        "[Zr+2]",
        "[Zr]",
        "[\\C]",
        "[\\I]",
        "[\\N]",
        "[\\O]",
    }
    result = exmol.run_stoned(
        "CCOC(=O)c1ccc(cc1)N=CN(C)c2ccccc2",
        num_samples=2500 // 2,
        max_mutations=2,
        alphabet=problem_alphabet,
        return_selfies=True,
    )
    # try to decode them all
    list([sf.decoder(s) for s in result[0]])


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


def test_sample_with_object():
    class A:
        def __call__(self, seqs):
            return [0 for _ in seqs]

    obj = A()
    exmol.sample_space("C", obj, batched=True)


def test_sample_with_partial():
    import functools

    def model(s, x):
        return int("N" in s)

    f = functools.partial(model, x=1)
    exmol.sample_space("C", f, batched=False)


def test_name_morgan_bit():
    mol = smi2mol("CO")
    bitInfo = {}
    AllChem.GetMorganFingerprintAsBitVect(mol, 2, bitInfo=bitInfo)
    name = exmol.name_morgan_bit(mol, bitInfo=bitInfo, key=1155)
    assert name == "alcohol"


def test_sample_multiple_bases():
    def model(s, se):
        return int("N" in s)

    s1 = exmol.sample_space("CCCC", model, preset="narrow", batched=False)
    s2 = exmol.sample_space("COC", model, preset="narrow", batched=False)
    all_s = s1 + s2
    betas = exmol.lime_explain(all_s, descriptor_type="ECFP", return_beta=True)
    exmol.plot_descriptors(all_s, "ECFP")

    # check if it inferred correctly
    assert np.allclose(
        betas,
        exmol.lime_explain(all_s, descriptor_type="ECFP", return_beta=True),
    )
    exmol.plot_descriptors(all_s, "ECFP")


def test_performance():
    def model(s, se):
        return int("F" in s)

    exps = exmol.sample_space(
        "O=C(NCC1CCCCC1N)C2=CC=CC=C2C3=CC=C(F)C=C3C(=O)NC4CCCCC4", model, batched=False
    )
    assert len(exps) > 2000
    cfs = exmol.cf_explain(exps)
    assert cfs[1].similarity > 0.5


def test_sample_chem():
    def model(s, se):
        return int("N" in s)

    explanation = exmol.sample_space(
        "CCCC", model, preset="chemed", batched=False, num_samples=35
    )
    # check that no redundants
    assert len(explanation) == len(set([e.smiles for e in explanation]))

    # try other keywords
    explanation = exmol.sample_space(
        "CCCC",
        model,
        preset="chemed",
        batched=False,
        num_samples=35,
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


def test_sample_synspace():
    def model(s, se):
        return int("N" in s)

    explanation = exmol.sample_space(
        "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C",
        model,
        preset="synspace",
        batched=False,
        num_samples=50,
    )
    # check that no redundants
    assert len(explanation) == 50


def test_cf_explain():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    exps = exmol.cf_explain(samples, 3)
    assert len(exps) == 4  # +1 for base

    exmol.cf_explain(samples, 3, False)
    exmol.cf_explain(samples, 3, True)


def test_cf_explain_split():
    def model(s, se):
        return int("N" in s)

    samples = exmol.sample_space("[Na+].CC(=O)CCCC", model, batched=False)
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
    exmol.lime_explain(samples, descriptor_type="ECFP", return_beta=True)


def test_text_explain():
    def model(s, se):
        return int("=O" in s)

    samples = exmol.sample_space("CCCC", model, batched=False)
    s = exmol.text_explain(samples, "MACCS")
    assert len(s) > 0, "No explanation generated"

    e = exmol.text_explain_generate(s, "soluble in water")

    samples1 = exmol.sample_space("c1cc(C(=O)O)c(OC(=O)C)cc1", model, batched=False)
    s = exmol.text_explain(samples1, "ECFP")
    assert len(s) > 0, "No explanation generated"

    samples2 = exmol.sample_space(
        "O=C(NCC1CCCCC1N)C2=CC=CC=C2C3=CC=C(F)C=C3C(=O)NC4CCCCC4", model, batched=False
    )

    # try with multiple origins
    samples = samples1 + samples2
    s1 = exmol.text_explain(samples, "ECFP")
    assert len(s1) > 0, 'No explanation found for "ECFP"'
    s2 = exmol.text_explain(samples, "MACCS")
    assert len(s2) > 0, 'No explanation found for "MACCS"'
    s = exmol.merge_text_explains(s1, s2)


def test_corrupt_smiles():
    def model(s, se):
        return int("N" in s)

    badsmi = "C/C=C/C(=O)C1CCC(C=C1C)(C)C"
    explanation = exmol.sample_space(badsmi, model, preset="narrow", batched=False)
    assert ~np.isnan(explanation[0].yhat)
