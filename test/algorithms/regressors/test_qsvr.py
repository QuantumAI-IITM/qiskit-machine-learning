# This code is part of a Qiskit project.
#
# (C) Copyright IBM 2021, 2024.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

""" Test QSVR """
import os
import tempfile
import unittest

from test import QiskitMachineLearningTestCase

import numpy as np
from sklearn.metrics import mean_squared_error

from qiskit.circuit.library import ZZFeatureMap
from qiskit_machine_learning.utils import algorithm_globals
from qiskit_machine_learning.algorithms import QSVR, SerializableModelMixin
from qiskit_machine_learning.exceptions import QiskitMachineLearningWarning
from qiskit_machine_learning.kernels import FidelityQuantumKernel


class TestQSVR(QiskitMachineLearningTestCase):
    """Test QSVR Algorithm"""

    def setUp(self):
        super().setUp()

        algorithm_globals.random_seed = 10598

        self.feature_map = ZZFeatureMap(feature_dimension=2, reps=2)

        num_samples_train = 10
        num_samples_test = 4
        eps = 0.2
        lb, ub = -np.pi, np.pi
        X_ = np.linspace(lb, ub, num=50).reshape(50, 1)
        f = lambda x: np.sin(x)

        X_train = (ub - lb) * algorithm_globals.random.random([num_samples_train, 1]) + lb
        y_train = f(X_train[:, 0]) + eps * (2 * algorithm_globals.random.random(num_samples_train) - 1)
        
        X_test = (ub - lb) * algorithm_globals.random.random([num_samples_test, 1]) + lb
        y_test = f(X_test[:, 0]) + eps * (2 * algorithm_globals.random.random(num_samples_test) - 1)

        self.sample_train = X_train
        self.label_train = y_train

        self.sample_test = X_test
        self.label_test = y_test

    def test_qsvr(self):
        """Test QSVR"""
        qkernel = FidelityQuantumKernel(feature_map=self.feature_map, enforce_psd=False)

        qsvr = QSVR(quantum_kernel=qkernel)
        qsvr.fit(self.sample_train, self.label_train)
        # score = qsvr.score(self.sample_test, self.label_test)
        # self.assertAlmostEqual(score, 0.38359, places=4)
        
        predictions = qsvr.predict(self.sample_test)
        score = mean_squared_error(self.label_test, predictions)
        self.assertLess(score, 0.05)

    def test_change_kernel(self):
        """Test QSVR with QuantumKernel later"""
        qkernel = FidelityQuantumKernel(feature_map=self.feature_map, enforce_psd=False)

        qsvr = QSVR()
        qsvr.quantum_kernel = qkernel
        qsvr.fit(self.sample_train, self.label_train)
        # score = qsvr.score(self.sample_test, self.label_test)

        # self.assertAlmostEqual(score, 0.38359, places=4)
        predictions = qsvr.predict(self.sample_test)
        score = mean_squared_error(self.label_test, predictions)
        self.assertLess(score, 0.05)
        
    def test_qsvr_parameters(self):
        """Test QSVR with extra constructor parameters"""

        qkernel = FidelityQuantumKernel(feature_map=self.feature_map)

        qsvr = QSVR(quantum_kernel=qkernel, tol=1e-4, C=0.5)
        qsvr.fit(self.sample_train, self.label_train)
        # score = qsvr.score(self.sample_test, self.label_test)

        # self.assertAlmostEqual(score, 0.38365, places=4)
        predictions = qsvr.predict(self.sample_test)
        score = mean_squared_error(self.label_test, predictions)
        self.assertLess(score, 0.05)

    def test_qsvc_to_string(self):
        """Test QSVR print works when no *args passed in"""
        qsvr = QSVR()
        _ = str(qsvr)

    def test_with_kernel_parameter(self):
        """Test QSVC with the `kernel` argument."""
        with self.assertWarns(QiskitMachineLearningWarning):
            QSVR(kernel=1)

    def test_save_load(self):
        """Tests save and load models."""
        features = np.array([[0, 0], [0.1, 0.1], [0.4, 0.4], [1, 1]])
        labels = np.array([0, 0.1, 0.4, 1])

        quantum_kernel = FidelityQuantumKernel(feature_map=ZZFeatureMap(2))
        regressor = QSVR(quantum_kernel=quantum_kernel)
        regressor.fit(features, labels)

        # predicted labels from the newly trained model
        test_features = np.array([[0.5, 0.5]])
        original_predicts = regressor.predict(test_features)

        # save/load, change the quantum instance and check if predicted values are the same
        with tempfile.TemporaryDirectory() as dir_name:
            file_name = os.path.join(dir_name, "qsvr.model")
            regressor.save(file_name)

            regressor_load = QSVR.load(file_name)
            loaded_model_predicts = regressor_load.predict(test_features)

            np.testing.assert_array_almost_equal(original_predicts, loaded_model_predicts)

            # test loading warning
            class FakeModel(SerializableModelMixin):
                """Fake model class for test purposes."""

                pass

            with self.assertRaises(TypeError):
                FakeModel.load(file_name)


if __name__ == "__main__":
    unittest.main()
