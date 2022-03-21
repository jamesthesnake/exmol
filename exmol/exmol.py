from typing import *

import itertools
import math
import requests  # type: ignore
import numpy as np
import matplotlib.pyplot as plt  # type: ignore
import matplotlib as mpl  # type: ignore
import selfies as sf  # type: ignore
import tqdm  # type: ignore

from ratelimit import limits, sleep_and_retry  # type: ignore
from sklearn.cluster import DBSCAN  # type: ignore
from sklearn.decomposition import PCA  # type: ignore
from rdkit.Chem import MolFromSmiles as smi2mol  # type: ignore
from rdkit.Chem import MolToSmiles as mol2smi  # type: ignore
from rdkit.Chem import rdchem  # type: ignore
from rdkit.Chem.Draw import MolToImage as mol2img  # type: ignore
from rdkit.Chem import rdFMCS as MCS  # type: ignore


from . import stoned
from .plot_utils import _mol_images, _image_scatter
from .data import *

_calculator = None


def _fp_dist_matrix(smiles, fp_type, _pbar):
    mols = [(smi2mol(s), _pbar.update(0.5))[0] for s in smiles]
    # Sorry about the one-line. Just sneaky insertion of progressbar update
    fp = [(stoned.get_fingerprint(m, fp_type), _pbar.update(0.5))[0] for m in mols]
    # 1 - Ts because we want distance
    dist = list(
        1 - stoned.TanimotoSimilarity(x, y) for x, y in itertools.product(fp, repeat=2)
    )
    return np.array(dist).reshape(len(mols), len(mols))


def _make_calculator():
    from mordred import HydrogenBond, Polarizability
    from mordred import SLogP, AcidBase, BertzCT, Aromatic, BondCount
    from mordred import Calculator
    c = Calculator()
    c.register([HydrogenBond.HBondDonor, HydrogenBond.HBondAcceptor])
    c.register([AcidBase.AcidicGroupCount, AcidBase.BasicGroupCount,
                Aromatic.AromaticBondsCount])
    c.register([SLogP.SLogP, Polarizability.APol,  BertzCT.BertzCT])
    c.register([BondCount.BondCount(type='double'),
                BondCount.BondCount(type='aromatic')])
    return c


def get_descriptors(examples: List[Example], 
                    descriptor_type: str = 'MACCS',
                    mols: List[Any] = None) -> List[Example]:
    """Returns set of descriptors for passed examples

    :param examples: List of example
    :param descriptor_type: Kind of descriptors to return, choose between 'Classic' and 'MACCS'. Default is 'MACCS'.
    :param mols: Can be used if you already have rdkit Mols computed.
    """
    import os
    from rdkit.Chem import MACCSkeys
    if mols is None:
        mols = [smi2mol(m.smiles) for m in examples]
    if descriptor_type == 'Classic':
        global _calculator
        if _calculator is None:
            _calculator = _make_calculator()
        names = tuple(d.description() for d in _calculator.descriptors)
        for e, c in zip(examples, _calculator.map(mols, quiet=True)):
            descriptors = tuple(v for v in c.values())
            descriptor_names = names
            e.descriptors = Descriptors(descriptors=descriptors, 
                                        descriptor_names=descriptor_names)
        return examples
    elif descriptor_type == 'MACCS':
        names = tuple([line.strip().split('\t')[-1]
                      for line 
                      in list(open(os.path.join(os.path.dirname(__file__),
                                                'MACCSkeys.txt')))[1:]])
        for e, m in zip(examples, mols):
            fps = list(MACCSkeys.GenMACCSKeys(m).ToBitString())
            descriptors = tuple(int(i) for i in fps)
            descriptor_names = names
            e.descriptors = Descriptors(descriptors=descriptors, 
                                        descriptor_names=descriptor_names)
        return examples
    else:
        raise ValueError('Invalid descriptor string. Valid descriptor strings are \'Classic\' and \'MACCS\'.')


def get_basic_alphabet() -> Set[str]:
    """Returns set of interpretable SELFIES tokens

    Generated by removing P and most ionization states from :func:`selfies.get_semantic_robust_alphabet`
    """
    a = sf.get_semantic_robust_alphabet()
    # remove cations/anions except oxygen anion
    to_remove = []
    for ai in a:
        if "+1" in ai:
            to_remove.append(ai)
        elif "-1" in ai:
            to_remove.append(ai)
    # remove [P],[#P],[=P]
    to_remove.extend(["[P]", "[#P]", "[=P]"])

    a -= set(to_remove)
    a.add("[O-1]")
    return a


def run_stoned(
    s: str,
    fp_type: str = "ECFP4",
    num_samples: int = 2000,
    max_mutations: int = 2,
    min_mutations: int = 1,
    alphabet: Union[List[str], Set[str]] = None,
    _pbar: Any = None,
) -> Tuple[List[str], List[float]]:
    """Run ths STONED SELFIES algorithm. Typically not used, call :func:`sample_space` instead.

    :param s: SMILES string to start from
    :param fp_type: Fingerprint type
    :param num_samples: Number of total molecules to generate
    :param max_mutations: Maximum number of mutations
    :param min_mutations: Minimum number of mutations
    :param alphabet: Alphabet to use for mutations, typically from :func:`get_basic_alphabet()`
    :return: SMILES and SCORES generated
    """
    if alphabet is None:
        alphabet = list(sf.get_semantic_robust_alphabet())
    if type(alphabet) == set:
        alphabet = list(alphabet)
    num_mutation_ls = list(range(min_mutations, max_mutations + 1))

    mol = smi2mol(s)
    if mol == None:
        raise Exception("Invalid starting structure encountered")

    # want it so after sampling have num_samples
    randomized_smile_orderings = [
        stoned.randomize_smiles(mol) for _ in range(num_samples // len(num_mutation_ls))
    ]

    # Convert all the molecules to SELFIES
    selfies_ls = [sf.encoder(x) for x in randomized_smile_orderings]

    all_smiles_collect: List[str] = []
    all_selfies_collect: List[str] = []
    for num_mutations in num_mutation_ls:
        # Mutate the SELFIES:
        if _pbar:
            _pbar.set_description(f"🥌STONED🥌 Mutations: {num_mutations}")
        selfies_mut = stoned.get_mutated_SELFIES(
            selfies_ls.copy(), num_mutations=num_mutations, alphabet=alphabet
        )
        # Convert back to SMILES:
        smiles_back = [sf.decoder(x) for x in selfies_mut]
        all_smiles_collect = all_smiles_collect + smiles_back
        all_selfies_collect = all_selfies_collect + selfies_mut
        if _pbar:
            _pbar.update(len(smiles_back))

    # Work on:  all_smiles_collect
    if _pbar:
        _pbar.set_description(f"🥌STONED🥌 Done")
    canon_smi_ls = []
    for item in all_smiles_collect:
        mol, smi_canon, did_convert = stoned.sanitize_smiles(item)
        if mol == None or smi_canon == "" or did_convert == False:
            raise Exception("Invalid smiles string found")
        canon_smi_ls.append(smi_canon)

    # remove redundant/non-unique/duplicates
    # in a way to keep the selfies
    canon_smi_ls = list(set(canon_smi_ls))

    canon_smi_ls_scores = stoned.get_fp_scores(
        canon_smi_ls, target_smi=s, fp_type=fp_type
    )
    # NOTE Do not think of returning selfies. They have duplicates
    return canon_smi_ls, canon_smi_ls_scores


FIFTEEN_MINUTES = 900


@sleep_and_retry
@limits(calls=50, period=FIFTEEN_MINUTES)
def run_chemed(
    origin_smiles: str,
    num_samples: int,
    similarity: float = 0.1,
    fp_type: str = "ECFP4",
    _pbar: Any = None,
) -> Tuple[List[str], List[float]]:
    """
    This method is similar to STONED but works by quering PubChem

    :param origin_smiles: Base SMILES
    :param num_samples: Minimum number of returned molecules. May return less due to network timeout or exhausting tree
    :param similarity: Tanimoto similarity to use in query (float between 0 to 1)
    :param fp_type: Fingerprint type
    :return: SMILES and SCORES
    """
    if _pbar:
        _pbar.set_description("⚡CHEMED⚡")
    else:
        print("⚡CHEMED⚡")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastsimilarity_2d/smiles/{requests.utils.quote(origin_smiles)}/property/CanonicalSMILES/JSON"
    try:
        reply = requests.get(
            url,
            params={"Threshold": int(similarity * 100), "MaxRecords": num_samples},
            headers={"accept": "text/json"},
            timeout=10,
        )
    except requests.exceptions.Timeout:
        print("Pubchem seems to be down right now ️☠️☠️")
        return [], []
    try:
        data = reply.json()
    except:
        return [], []
    smiles = [d["CanonicalSMILES"] for d in data["PropertyTable"]["Properties"]]
    smiles = list(set(smiles))

    if _pbar:
        _pbar.set_description(f"Received {len(smiles)} similar molecules")

    mol0 = smi2mol(origin_smiles)
    mols = [smi2mol(s) for s in smiles]
    fp0 = stoned.get_fingerprint(mol0, fp_type)
    scores = []
    # drop Nones
    smiles = [s for s, m in zip(smiles, mols) if m is not None]
    for m in mols:
        if m is None:
            continue
        fp = stoned.get_fingerprint(m, fp_type)
        scores.append(stoned.TanimotoSimilarity(fp0, fp))
        if _pbar:
            _pbar.update()
    return smiles, scores


def run_custom(
    origin_smiles: str,
    data: List[Union[str, rdchem.Mol]],
    fp_type: str = "ECFP4",
    _pbar: Any = None,
    **kwargs,
) -> Tuple[List[str], List[float]]:
    """
    This method is similar to STONED but uses a custom dataset provided by the user

    :param origin_smiles: Base SMILES
    :param data: List of SMILES or RDKit molecules
    :param fp_type: Fingerprint type
    :return: SMILES and SCORES
    """
    if _pbar:
        _pbar.set_description("⚡CUSTOM⚡")
    else:
        print("⚡CUSTOM⚡")
    mol0 = smi2mol(origin_smiles)
    fp0 = stoned.get_fingerprint(mol0, fp_type)
    scores = []
    smiles = []
    # drop invalid molecules
    for d in data:
        if isinstance(d, str):
            m = smi2mol(d)
        else:
            m = d
        if m is None:
            continue
        smiles.append(mol2smi(m))
        fp = stoned.get_fingerprint(m, fp_type)
        scores.append(stoned.TanimotoSimilarity(fp0, fp))
        if _pbar:
            _pbar.update()
    return smiles, scores


def sample_space(
    origin_smiles: str,
    f: Union[
        Callable[[List[str], List[str]], List[float]],
        Callable[[List[str], List[str]], List[float]],
    ],
    batched: bool = True,
    preset: str = "medium",
    data: List[Union[str, rdchem.Mol]] = None,
    method_kwargs: Dict = None,
    num_samples: int = None,
    stoned_kwargs: Dict = None,
) -> List[Example]:
    """Sample chemical space around given SMILES

    This will evaluate the given function and run the :func:`run_stoned` function over chemical space around molecule. ``num_samples`` will be
    set to 3,000 by default if using STONED and 150 if using ``chemed``.

    :param origin_smiles: starting SMILES
    :param f: A function which takes in SMILES and SELFIES and returns predicted value. Assumed to work with lists of SMILES/SELFIES unless `batched = False`
    :param batched: If `f` is batched
    :param preset: Can be wide, medium, or narrow. Determines how far across chemical space is sampled. Try `"chemed"` preset to only sample commerically available compounds.
    :param data: If not None and preset is `"custom"` will use this data instead of generating new ones.
    :param method_kwargs: More control over STONED, CHEMED and CUSTOM can be set here. See :func:`run_stoned`, :func:`run_chemed` and  :func:`run_custom`
    :param num_samples: Number of desired samples. Can be set in `method_kwargs` (overrides) or here. `None` means default for preset
    :param stoned_kwargs: Backwards compatible alias for `methods_kwargs`
    :return: List of generated :obj:`Example`
    """
    batched_f = f
    if not batched:

        def batched_f(sm, se):
            return np.array([f(smi, sei) for smi, sei in zip(sm, se)])

    origin_smiles = stoned.sanitize_smiles(origin_smiles)[1]
    if origin_smiles is None:
        raise ValueError("Given SMILES does not appear to be valid")
    smi_yhat = np.asarray(batched_f([origin_smiles], [sf.encoder(origin_smiles)]))
    try:
        iter(smi_yhat)
    except TypeError:
        raise ValueError("Your model function does not appear to be batched")
    smi_yhat = np.squeeze(smi_yhat[0])

    if stoned_kwargs is not None:
        method_kwargs = stoned_kwargs

    if method_kwargs is None:
        method_kwargs = {}
        if preset == "medium":
            method_kwargs["num_samples"] = 3000 if num_samples is None else num_samples
            method_kwargs["max_mutations"] = 2
            method_kwargs["alphabet"] = get_basic_alphabet()
        elif preset == "narrow":
            method_kwargs["num_samples"] = 3000 if num_samples is None else num_samples
            method_kwargs["max_mutations"] = 1
            method_kwargs["alphabet"] = get_basic_alphabet()
        elif preset == "wide":
            method_kwargs["num_samples"] = 3000 if num_samples is None else num_samples
            method_kwargs["max_mutations"] = 5
            method_kwargs["alphabet"] = sf.get_semantic_robust_alphabet()
        elif preset == "chemed":
            method_kwargs["num_samples"] = 150 if num_samples is None else num_samples
        elif preset == "custom" and data is not None:
            method_kwargs["num_samples"] = len(data)
        else:
            raise ValueError(f'Unknown preset "{preset}"')
    try:
        num_samples = method_kwargs["num_samples"]
    except KeyError as e:
        if num_samples is None:
            num_samples = 150
        method_kwargs["num_samples"] = num_samples

    pbar = tqdm.tqdm(total=num_samples)

    # STONED
    if preset.startswith("chem"):
        smiles, scores = run_chemed(origin_smiles, _pbar=pbar, **method_kwargs)
    elif preset == "custom":
        smiles, scores = run_custom(
            origin_smiles, data=cast(Any, data), _pbar=pbar, **method_kwargs
        )
    else:
        smiles, scores = run_stoned(origin_smiles, _pbar=pbar, **method_kwargs)
    selfies = [sf.encoder(s) for s in smiles]

    pbar.set_description("😀Calling your model function😀")
    fxn_values = batched_f(smiles, selfies)

    # pack them into data structure with filtering out identical
    # and nan
    exps = [
        Example(
            origin_smiles,
            sf.encoder(origin_smiles),
            1.0,
            cast(Any, smi_yhat),
            index=0,
            is_origin=True,
        )
    ] + [
        Example(sm, se, s, cast(Any, np.squeeze(y)), index=0)
        for i, (sm, se, s, y) in enumerate(zip(smiles, selfies, scores, fxn_values))
        if s < 1.0 and np.isfinite(np.squeeze(y))
    ]

    for i, e in enumerate(exps):  # type: ignore
        e.index = i  # type: ignore

    pbar.reset(len(exps))
    pbar.set_description("🔭Projecting...🔭")

    # compute distance matrix
    full_dmat = _fp_dist_matrix(
        [e.smiles for e in exps],
        method_kwargs["fp_type"] if ("fp_type" in method_kwargs) else "ECFP4",
        _pbar=pbar,
    )

    pbar.set_description("🥰Finishing up🥰")

    # compute PCA
    pca = PCA(n_components=2)
    proj_dmat = pca.fit_transform(full_dmat)
    for e in exps:  # type: ignore
        e.position = proj_dmat[e.index, :]  # type: ignore

    # do clustering everwhere (maybe do counter/same separately?)
    # clustering = AgglomerativeClustering(
    #    n_clusters=max_k, affinity='precomputed', linkage='complete').fit(full_dmat)
    # Just do it on projected so it looks prettier.
    clustering = DBSCAN(eps=0.15, min_samples=5).fit(proj_dmat)

    for i, e in enumerate(exps):  # type: ignore
        e.cluster = clustering.labels_[i]  # type: ignore

    pbar.set_description("🤘Done🤘")
    pbar.close()
    return exps


def _select_examples(cond, examples, nmols):
    result = []

    # similarity filtered by if cluster/counter
    def cluster_score(e, i):
        return (e.cluster == i) * cond(e) * e.similarity

    clusters = set([e.cluster for e in examples])
    for i in clusters:
        close_counter = max(examples, key=lambda e, i=i: cluster_score(e, i))
        # check if actually is (since call could have been zero)
        if cluster_score(close_counter, i):
            result.append(close_counter)

    # trim, in case we had too many cluster
    result = sorted(result, key=lambda v: v.similarity * cond(v), reverse=True)[:nmols]

    # fill in remaining
    ncount = sum([cond(e) for e in result])
    fill = max(0, nmols - ncount)
    result.extend(
        sorted(examples, key=lambda v: v.similarity * cond(v), reverse=True)[:fill]
    )

    return list(filter(cond, result))


def lime_explain(examples: List[Example], descriptor_type: str) -> np.ndarray:
    # TODO: return something more useful
    try:
        # try last, since base may have had descriptors
        M = len(examples[-1].descriptors)
    except TypeError:
        # descriptors need to be calculated
        examples = get_descriptors(examples, descriptor_type)
        M = len(examples[-1].descriptors.descriptors)

    x_mat = np.array([list(e.descriptors.descriptors)
                      for e in examples]).reshape(len(examples), -1)
    # remove zero variance columns
    y = np.array([e.yhat for e in examples]).reshape(
        len(examples)).astype(float)
    # sqrt to weights for lstq equation
    # w = np.sqrt([e.similarity for e in examples])
    w = np.array([1/(1 + (1/(e.similarity + 0.000001) - 1)**5)
                  for e in examples])
    # create a diagonal matrix of w
    N = x_mat.shape[0]
    diag_w = np.zeros((N, N)) 
    np.fill_diagonal(diag_w, w)
    # remove bias
    y -= np.mean(y)
    # compute least squares fit
    xtinv = np.linalg.pinv((x_mat.T @ diag_w @ x_mat ))
    beta = xtinv @ x_mat.T @ (y * w)
    # compute tstats for each example as a difference from base
    for e in examples:
        e.descriptors.tstats = e.descriptors.descriptors * beta
    # compute standard error in beta
    yhat = x_mat @ beta
    resids = yhat - y
    SSR = np.sum(resids**2)
    se2_epsilon = SSR / (len(examples) - len(beta))
    se2_beta = se2_epsilon * xtinv
    # now compute t-statistic for existence of coefficients
    tstat = beta * np.sqrt(1 / np.diag(se2_beta))
    # Return tstats of the space and beta (feature weights) which are the fits
    return tstat, beta


def cf_explain(examples: List[Example], nmols: int = 3) -> List[Example]:
    """From given :obj:`Examples<Example>`, find closest counterfactuals (see :doc:`index`)

    :param examples: Output from :func:`sample_space`
    :param nmols: Desired number of molecules
    """

    def is_counter(e):
        return e.yhat != examples[0].yhat

    result = _select_examples(is_counter, examples[1:], nmols)
    for i, r in enumerate(result):
        r.label = f"Counterfactual {i+1}"

    return examples[:1] + result


def rcf_explain(
    examples: List[Example],
    delta: Union[Any, Tuple[float, float]] = (-1, 1),
    nmols: int = 4,
) -> List[Example]:
    """From given :obj:`Examples<Example>`, find closest counterfactuals (see :doc:`index`)
    This version works with regression, so that a counterfactual is if the given example is higher or
    lower than base.

    :param examples: Output from :func:`sample_space`
    :param delta: float or tuple of hi/lo indicating margin for what is counterfactual
    :param nmols: Desired number of molecules
    """
    if type(delta) is float:
        delta = (-delta, delta)

    def is_high(e):
        return e.yhat + delta[0] >= examples[0].yhat

    def is_low(e):
        return e.yhat + delta[1] <= examples[0].yhat

    hresult = (
        [] if delta[0] is None else _select_examples(is_high, examples[1:], nmols // 2)
    )
    for i, h in enumerate(hresult):
        h.label = f"Increase ({i+1})"
    lresult = (
        [] if delta[1] is None else _select_examples(is_low, examples[1:], nmols // 2)
    )
    for i, l in enumerate(lresult):
        l.label = f"Decrease ({i+1})"
    return examples[:1] + lresult + hresult


def plot_space(
    examples: List[Example],
    exps: List[Example],
    figure_kwargs: Dict = None,
    mol_size: Tuple[int, int] = (200, 200),
    highlight_clusters: bool = False,
    mol_fontsize: int = 8,
    offset: int = 0,
    ax: Any = None,
    cartoon: bool = False,
    rasterized: bool = False,
):
    """Plot chemical space around example and annotate given examples.

    :param examples: Large list of :obj:Example which make-up points
    :param exps: Small list of :obj:Example which will be annotated
    :param figure_kwargs: kwargs to pass to :func:`plt.figure<matplotlib.pyplot.figure>`
    :param mol_size: size of rdkit molecule rendering, in pixles
    :param highlight_clusters: if `True`, cluster indices are rendered instead of :obj:Example.yhat
    :param mol_fontsize: minimum font size passed to rdkit
    :param offset: offset annotations to allow colorbar or other elements to fit into plot.
    :param ax: axis onto which to plot
    :param cartoon: do cartoon outline on points?
    :param rasterized: raster the scatter?
    """
    imgs = _mol_images(exps, mol_size, mol_fontsize)#, True)
    if figure_kwargs is None:
        figure_kwargs = {"figsize": (12, 8)}
    base_color = "gray"
    if ax is None:
        ax = plt.figure(**figure_kwargs).gca()
    if highlight_clusters:
        colors = [e.cluster for e in examples]

        def normalizer(x):
            return x

        cmap = "Accent"

    else:
        colors = cast(Any, [e.yhat for e in examples])
        normalizer = plt.Normalize(min(colors), max(colors))
        cmap = "viridis"
    space_x = [e.position[0] for e in examples]
    space_y = [e.position[1] for e in examples]
    if cartoon:
        # plot shading, lines, front
        ax.scatter(space_x, space_y, 50, "0.0", lw=2, rasterized=rasterized)
        ax.scatter(space_x, space_y, 50, "1.0", lw=0, rasterized=rasterized)
        ax.scatter(
            space_x,
            space_y,
            40,
            c=normalizer(colors),
            cmap=cmap,
            lw=2,
            alpha=0.1,
            rasterized=rasterized,
        )
    else:
        ax.scatter(
            space_x,
            space_y,
            c=normalizer(colors),
            cmap=cmap,
            alpha=0.5,
            edgecolors="none",
            rasterized=rasterized,
        )
    # now plot cfs/annotated points
    ax.scatter(
        [e.position[0] for e in exps],
        [e.position[1] for e in exps],
        c=normalizer([e.cluster if highlight_clusters else e.yhat for e in exps]),
        cmap=cmap,
        edgecolors="black",
    )

    x = [e.position[0] for e in exps]
    y = [e.position[1] for e in exps]
    titles = []
    colors = []
    for e in exps:
        if not e.is_origin:
            titles.append(f"Similarity = {e.similarity:.2f}\n{e.label}")
            colors.append(cast(Any, base_color))
        else:
            titles.append("Base")
            colors.append(cast(Any, base_color))
    _image_scatter(x, y, imgs, titles, colors, ax, offset=offset)
    ax.axis("off")
    ax.set_aspect("auto")


def plot_cf(
    exps: List[Example],
    fig: Any = None,
    figure_kwargs: Dict = None,
    mol_size: Tuple[int, int] = (200, 200),
    mol_fontsize: int = 10,
    nrows: int = None,
    ncols: int = None,
):
    """Draw the given set of Examples in a grid

    :param exps: Small list of :obj:`Example` which will be drawn
    :param fig: Figure to plot onto
    :param figure_kwargs: kwargs to pass to :func:`plt.figure<matplotlib.pyplot.figure>`
    :param mol_size: size of rdkit molecule rendering, in pixles
    :param mol_fontsize: minimum font size passed to rdkit
    :param nrows: number of rows to draw in grid
    :param ncols: number of columns to draw in grid
    """
    imgs = _mol_images(exps, mol_size, mol_fontsize, True)
    if nrows is not None:
        R = nrows
    else:
        R = math.ceil(math.sqrt(len(imgs)))
    if ncols is not None:
        C = ncols
    else:
        C = math.ceil(len(imgs) / R)
    if fig is None:
        if figure_kwargs is None:
            figure_kwargs = {"figsize": (12, 8)}
        fig, axs = plt.subplots(R, C, **figure_kwargs)
    else:
        axs = fig.subplots(R, C)
    axs = axs.flatten()
    for i, (img, e) in enumerate(zip(imgs, exps)):
        title = "Base" if e.is_origin else f"Similarity = {e.similarity:.2f}\n{e.label}"
        title += f"\nf(x) = {e.yhat:.3f}"
        axs[i].set_title(title)
        axs[i].imshow(np.asarray(img), gid=f"rdkit-img-{i}")
        axs[i].axis("off")
    for j in range(i, C * R):
        axs[j].axis("off")
        axs[j].set_facecolor("white")
    plt.tight_layout()
