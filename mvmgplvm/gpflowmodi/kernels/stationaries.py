# Copyright 2017-2020 The GPflow Contributors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np
import tensorflow as tf

from ..base import Parameter
from ..utilities import positive
from ..utilities.ops import difference_matrix, square_distance
from .base import Kernel


class Stationary(Kernel):
    """
    Base class for kernels that are stationary, that is, they only depend on

        d = x - x'

    This class handles 'ard' behaviour, which stands for 'Automatic Relevance
    Determination'. This means that the kernel has one lengthscale per
    dimension, otherwise the kernel is isotropic (has a single lengthscale).
    """

    def __init__(self, variance=1.0, lengthscales=1.0, **kwargs):
        """
        :param variance: the (initial) value for the variance parameter.
        :param lengthscales: the (initial) value for the lengthscale
            parameter(s), to induce ARD behaviour this must be initialised as
            an array the same length as the the number of active dimensions
            e.g. [1., 1., 1.]. If only a single value is passed, this value
            is used as the lengthscale of each dimension.
        :param kwargs: accepts `name` and `active_dims`, which is a list or
            slice of indices which controls which columns of X are used (by
            default, all columns are used).
        """
        for kwarg in kwargs:
            if kwarg not in {"name", "active_dims"}:
                raise TypeError(f"Unknown keyword argument: {kwarg}")

        super().__init__(**kwargs)
        self.variance = Parameter(variance, transform=positive())
        self.lengthscales = Parameter(lengthscales, transform=positive())
        self._validate_ard_active_dims(self.lengthscales)

    @property
    def ard(self) -> bool:
        """
        Whether ARD behaviour is active.
        """
        return self.lengthscales.shape.ndims > 0

    def scale(self, X):
        X_scaled = X / self.lengthscales if X is not None else X
        return X_scaled

    def K_diag(self, X):
        return tf.fill(tf.shape(X)[:-1], tf.squeeze(self.variance))


class IsotropicStationary(Stationary):
    """
    Base class for isotropic stationary kernels, i.e. kernels that only
    depend on

        r = ???x - x'???

    Derived classes should implement one of:

        K_r2(self, r2): Returns the kernel evaluated on r?? (r2), which is the
        squared scaled Euclidean distance Should operate element-wise on r2.

        K_r(self, r): Returns the kernel evaluated on r, which is the scaled
        Euclidean distance. Should operate element-wise on r.
    """

    def K(self, X, X2=None):
        r2 = self.scaled_squared_euclid_dist(X, X2)
        return self.K_r2(r2)

    def K_r2(self, r2):
        if hasattr(self, "K_r"):
            # Clipping around the (single) float precision which is ~1e-45.
            r = tf.sqrt(tf.maximum(r2, 1e-36))
            return self.K_r(r)  # pylint: disable=no-member
        raise NotImplementedError

    def scaled_squared_euclid_dist(self, X, X2=None):
        """
        Returns ???(X - X2???) / ????????, i.e. the squared L???-norm.
        """
        return square_distance(self.scale(X), self.scale(X2))


class AnisotropicStationary(Stationary):
    """
    Base class for anisotropic stationary kernels, i.e. kernels that only
    depend on

        d = x - x'

    Derived classes should implement K_d(self, d): Returns the kernel evaluated
    on d, which is the pairwise difference matrix, scaled by the lengthscale
    parameter ??? (i.e. [(X - X2???) / ???]). The last axis corresponds to the
    input dimension.
    """

    def K(self, X, X2=None):
        return self.K_d(self.scaled_difference_matrix(X, X2))

    def scaled_difference_matrix(self, X, X2=None):
        """
        Returns [(X - X2???) / ???]. If X has shape [..., N, D] and
        X2 has shape [..., M, D], the output will have shape [..., N, M, D].
        """
        return difference_matrix(self.scale(X), self.scale(X2))

    def K_d(self, d):
        raise NotImplementedError


class SquaredExponential(IsotropicStationary):
    """
    The radial basis function (RBF) or squared exponential kernel. The kernel equation is

        k(r) = ???? exp{-?? r??}

    where:
    r   is the Euclidean distance between the input points, scaled by the lengthscales parameter ???.
    ????  is the variance parameter

    Functions drawn from a GP with this kernel are infinitely differentiable!
    """

    def K_r2(self, r2):
        return self.variance * tf.exp(-0.5 * r2)


class RationalQuadratic(IsotropicStationary):
    """
    Rational Quadratic kernel,

    k(r) = ???? (1 + r?? / 2???????)^(-??)

    ???? : variance
    ???  : lengthscales
    ??  : alpha, determines relative weighting of small-scale and large-scale fluctuations

    For ?? ??? ???, the RQ kernel becomes equivalent to the squared exponential.
    """

    def __init__(self, variance=1.0, lengthscales=1.0, alpha=1.0, active_dims=None):
        super().__init__(variance=variance, lengthscales=lengthscales, active_dims=active_dims)
        self.alpha = Parameter(alpha, transform=positive())

    def K_r2(self, r2):
        return self.variance * (1 + 0.5 * r2 / self.alpha) ** (-self.alpha)


class Exponential(IsotropicStationary):
    """
    The Exponential kernel. It is equivalent to a Matern12 kernel with doubled lengthscales.
    """

    def K_r(self, r):
        return self.variance * tf.exp(-0.5 * r)


class Matern12(IsotropicStationary):
    """
    The Matern 1/2 kernel. Functions drawn from a GP with this kernel are not
    differentiable anywhere. The kernel equation is

    k(r) = ???? exp{-r}

    where:
    r  is the Euclidean distance between the input points, scaled by the lengthscales parameter ???.
    ???? is the variance parameter
    """

    def K_r(self, r):
        return self.variance * tf.exp(-r)


class Matern32(IsotropicStationary):
    """
    The Matern 3/2 kernel. Functions drawn from a GP with this kernel are once
    differentiable. The kernel equation is

    k(r) = ???? (1 + ???3r) exp{-???3 r}

    where:
    r  is the Euclidean distance between the input points, scaled by the lengthscales parameter ???,
    ???? is the variance parameter.
    """

    def K_r(self, r):
        sqrt3 = np.sqrt(3.0)
        return self.variance * (1.0 + sqrt3 * r) * tf.exp(-sqrt3 * r)


class Matern52(IsotropicStationary):
    """
    The Matern 5/2 kernel. Functions drawn from a GP with this kernel are twice
    differentiable. The kernel equation is

    k(r) = ???? (1 + ???5r + 5/3r??) exp{-???5 r}

    where:
    r  is the Euclidean distance between the input points, scaled by the lengthscales parameter ???,
    ???? is the variance parameter.
    """

    def K_r(self, r):
        sqrt5 = np.sqrt(5.0)
        return self.variance * (1.0 + sqrt5 * r + 5.0 / 3.0 * tf.square(r)) * tf.exp(-sqrt5 * r)


class Cosine(AnisotropicStationary):
    """
    The Cosine kernel. Functions drawn from a GP with this kernel are sinusoids
    (with a random phase).  The kernel equation is

        k(r) = ???? cos{2??d}

    where:
    d  is the sum of the per-dimension differences between the input points, scaled by the
    lengthscale parameter ??? (i.e. ????? [(X - X2???) / ???]???),
    ???? is the variance parameter.
    """

    def K_d(self, d):
        d = tf.reduce_sum(d, axis=-1)
        return self.variance * tf.cos(2 * np.pi * d)
