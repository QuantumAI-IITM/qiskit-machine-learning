# This code is part of a Qiskit project.
#
# (C) Copyright IBM 2018, 2024.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""

Ad Hoc Dataset

"""
from __future__ import annotations
from functools import reduce
import itertools as it
from typing import Tuple, Dict, List
import numpy as np
from sklearn import preprocessing
from qiskit.utils import optionals
from ..utils import algorithm_globals
from scipy.stats.qmc import Sobol

# pylint: disable=too-many-positional-arguments
def ad_hoc_data(
    train_size: int,
    test_size: int,
    n: int,
    gap: int,
    divisions: int = 0,
    plot_data: bool = False,
    one_hot: bool = True,
    include_sample_total: bool = False,
) -> (
    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    | Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
):
    r"""Generates a toy dataset that can be fully separated with
    :class:`~qiskit.circuit.library.ZZFeatureMap` according to the procedure
    outlined in [1]. To construct the dataset, we first sample uniformly
    distributed vectors :math:`\vec{x} \in (0, 2\pi]^{n}` and apply the
    feature map

    .. math::
        |\Phi(\vec{x})\rangle = U_{{\Phi} (\vec{x})} H^{\otimes n} U_{{\Phi} (\vec{x})}
        H^{\otimes n} |0^{\otimes n} \rangle

    where

    .. math::
        U_{{\Phi} (\vec{x})} = \exp \left( i \sum_{S \subseteq [n] } \phi_S(\vec{x})
        \prod_{i \in S} Z_i \right)

    and

    .. math::
        \begin{cases}
        \phi_{\{i, j\}} = (\pi - x_i)(\pi - x_j) \\
        \phi_{\{i\}} = x_i
        \end{cases}

    We then attribute labels to the vectors according to the rule

    .. math::
        m(\vec{x}) = \begin{cases}
        1 & \langle \Phi(\vec{x}) | V^\dagger \prod_i Z_i V | \Phi(\vec{x}) \rangle > \Delta \\
        -1 & \langle \Phi(\vec{x}) | V^\dagger \prod_i Z_i V | \Phi(\vec{x}) \rangle < -\Delta
        \end{cases}

    where :math:`\Delta` is the separation gap, and
    :math:`V\in \mathrm{SU}(4)` is a random unitary.

    **References:**

    [1] Havlíček V, Córcoles AD, Temme K, Harrow AW, Kandala A, Chow JM,
    Gambetta JM. Supervised learning with quantum-enhanced feature
    spaces. Nature. 2019 Mar;567(7747):209-12.
    `arXiv:1804.11326 <https://arxiv.org/abs/1804.11326>`_

    Args:
        training_size: the number of training samples.
        test_size: the number of testing samples.
        n: number of qubits (dimension of the feature space). 
        gap: separation gap (:math:`\Delta`).
        divisions: non-zero value does 1D stratified sampling.
            This defaults to zero which will set this to Sobol sampling.
            It's recommended to have a total number of datapoints = 2^n
            for Sobol sampling
        plot_data: whether to plot the data. Requires matplotlib.
        one_hot: if True, return the data in one-hot format.
        include_sample_total: if True, return all points in the uniform
            grid in addition to training and testing samples.

    Returns:
        Training and testing samples.

    Raises:
        ValueError: if n is not 2 or 3.
    """

    class_labels = [r"A", r"B"]

    # Initial State
    dims = 2**n
    psi_0 = np.ones(dims) / np.sqrt(dims)

    # n-qubit Hadamard
    h_n = n_hadamard(n)

    # Single qubit Z gates
    z_diags = np.array([np.diag(_i_z(i,n)).reshape((1,-1)) for i in range(n)])

    # Precompute Pairwise ZZ block diagonals
    zz_diags = {}
    for (i, j) in combinations(range(n), 2):
        zz_diags[(i, j)] = z_diags[i] * z_diags[j] 

    # n-qubit Z gate: notice that h_n[0,:] has the same elements as diagonal of z_n
    z_n = _n_z(h_n)

    # V change of basis: Eigenbasis of a random hermitian will be a random unitary
    A = np.array(algorithm_globals.random.random((dims, )) 
                + 1j * algorithm_globals.random.random((dims, dims)))
    Herm = A.conj().T @ A 
    eigvals, eigvecs = np.linalg.eig(Herm)
    idx = eigvals.argsort()[::-1]
    V = eigvecs[:, idx]

    # Observable for labelling boundary
    O = V.conj().T @ z_n @ V

    # Stratified Sampling for x vector
    n_samples = train_size+test_size
    if divisions>0: x_vecs = _modified_LHC(n, n_samples, divisions)
    else: x_vecs = _sobol_sampling(n, n_samples) 

    # Seperable ZZFeaturemap: exp(sum j phi Zi + sum j phi Zi Zj)
    ind_pairs = zz_diags.keys()
    pre_exp = np.zeros((n_samples, dims))

    # First Order Terms
    for i in range(n):
        pre_exp += _phi_i(x_vecs, i)*z_diags[i]
    # Second Order Terms 
    for (i,j) in ind_pairs:
        pre_exp += _phi_ij(x_vecs, i, j)*zz_diags[(i,j)]
    
    # Since pre_exp is purely diagonal, exp(A) = diag(exp(Aii))
    post_exp = np.exp(1j * pre_exp)
    Uphi = np.zeros((10, dims, dims), dtype = post_exp.dtype)
    cols = range(dims)
    Uphi[:,cols, cols] = post_exp[:, cols]

    Psi = (Uphi @ h_n @ Uphi @ psi_0).reshape((-1, dims, 1))

    # Labelling
    Psi_dag = np.transpose(Psi.conj(), (0, 2, 1))
    exp_val = np.real(Psi_dag @ O @ Psi)
    
    if np.abs(exp_val) > gap:
        _sample_total.append(np.sign(exp_val))
    else:
        _sample_total.append(0)
    sample_total = np.array(_sample_total).reshape(*[count] * n)

    # Extract training and testing samples from grid
    x_sample, y_sample = _sample_ad_hoc_data(sample_total, xvals, training_size + test_size, n)

    if plot_data:
        _plot_ad_hoc_data(x_sample, y_sample, training_size)

    training_input = {
        key: (x_sample[y_sample == k, :])[:training_size] for k, key in enumerate(class_labels)
    }
    test_input = {
        key: (x_sample[y_sample == k, :])[training_size : (training_size + test_size)]
        for k, key in enumerate(class_labels)
    }

    training_feature_array, training_label_array = _features_and_labels_transform(
        training_input, class_labels, one_hot
    )
    test_feature_array, test_label_array = _features_and_labels_transform(
        test_input, class_labels, one_hot
    )

    if include_sample_total:
        return (
            training_feature_array,
            training_label_array,
            test_feature_array,
            test_label_array,
            sample_total,
        )
    else:
        return (
            training_feature_array,
            training_label_array,
            test_feature_array,
            test_label_array,
        )


def _sample_ad_hoc_data(sample_total, xvals, num_samples, n):
    count = sample_total.shape[0]
    sample_a, sample_b = [], []
    for i, sample_list in enumerate([sample_a, sample_b]):
        label = 1 if i == 0 else -1
        while len(sample_list) < num_samples:
            draws = tuple(algorithm_globals.random.choice(count) for i in range(n))
            if sample_total[draws] == label:
                sample_list.append([xvals[d] for d in draws])

    labels = np.array([0] * num_samples + [1] * num_samples)
    samples = [sample_a, sample_b]
    samples = np.reshape(samples, (2 * num_samples, n))
    return samples, labels


@optionals.HAS_MATPLOTLIB.require_in_call
def _plot_ad_hoc_data(x_total, y_total, training_size):
    import matplotlib.pyplot as plt

    n = x_total.shape[1]
    fig = plt.figure()
    projection = "3d" if n == 3 else None
    ax1 = fig.add_subplot(1, 1, 1, projection=projection)
    for k in range(0, 2):
        ax1.scatter(*x_total[y_total == k][:training_size].T)
    ax1.set_title("Ad-hoc Data")
    plt.show()


def _features_and_labels_transform(
    dataset: Dict[str, np.ndarray], class_labels: List[str], one_hot: bool = True
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Converts a dataset into arrays of features and labels.

    Args:
        dataset: A dictionary in the format of {'A': numpy.ndarray, 'B': numpy.ndarray, ...}
        class_labels: A list of classes in the dataset
        one_hot (bool): if True - return one-hot encoded label

    Returns:
        A tuple of features as np.ndarray, label as np.ndarray
    """
    features = np.concatenate(list(dataset.values()))

    raw_labels = []
    for category in dataset.keys():
        num_samples = dataset[category].shape[0]
        raw_labels += [category] * num_samples

    if not raw_labels:
        # no labels, empty dataset
        labels = np.zeros((0, len(class_labels)))
        return features, labels

    if one_hot:
        encoder = preprocessing.OneHotEncoder()
        encoder.fit(np.array(class_labels).reshape(-1, 1))
        labels = encoder.transform(np.array(raw_labels).reshape(-1, 1))
        if not isinstance(labels, np.ndarray):
            labels = np.array(labels.todense())
    else:
        encoder = preprocessing.LabelEncoder()
        encoder.fit(np.array(class_labels))
        labels = encoder.transform(np.array(raw_labels))

    return features, labels

def _n_hadamard(n: int):
    
    base = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
    result = 1
    expo = n

    while expo>0:
        if expo%2==1:
            result = np.kron(result, base)
        base = np.kron(base, base)
        expo //= 2

    return result

def _i_z(i: int, n: int):

    z = np.diag([1, -1])
    i_1 = np.eye(2**i)
    i_2 = np.eye(2**(n-i-1))

    result = np.kron(i_1,z)
    result = np.kron(result, i_2)

    return result
    
def _n_z(h_n: np.ndarray):
    res = np.diag(h_n)
    res = np.sign(res)
    res = np.diag(res)
    return res

def _modified_LHC(n:int, n_samples:int, n_div:int):
    samples = np.empty((n_samples,n),dtype = float)
    bin_size = 2*np.pi/n_div
    n_passes = (n_samples+n_div-1)//n_div

    all_bins = np.tile(np.arange(n_div),n_passes)

    for dim in range(n):
        algorithm_globals.random.shuffle(all_bins)
        chosen_bins = all_bins[:n_samples]
        offsets = algorithm_globals.random.random(n_samples)
        samples[:, dim] = (chosen_bins+offsets)*bin_size

    return samples

def _sobol_sampling(n, n_samples):
    sampler = Sobol(d=n, scramble=True)
    p = 2*np.pi*sampler.random(n_samples)
    return p

def _phi_i(x_vecs: np.ndarray, i: int):
    return x_vecs[:,i].reshape((-1,1))

def _phi_ij(x_vecs: np.ndarray, i: int, j: int):
    return ((np.pi - x_vecs[:,i])*(np.pi - x_vecs[:,j])).reshape((-1,1))

print(ad_hoc_data(10,10,3,10,0))