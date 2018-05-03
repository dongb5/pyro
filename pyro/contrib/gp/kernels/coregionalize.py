from __future__ import absolute_import, division, print_function

import torch
from torch.distributions import constraints
from torch.nn import Parameter

from .kernel import Kernel


class Coregionalize(Kernel):
    r"""
    A kernel for the linear model of coregionalization
    :math:`k(x,z) = x^T (C C^T + D) z` where :math:`C` is an
    ``input_dim``-by-``rank`` matrix and typically ``rank < input_dim``,
    and ``D`` is a diagonal matrix.

    This generalizes the
    :class:`~pyro.contrib.gp.kernels.dot_product.Linear` kernel to multiple
    features with a low-rank-plus-diagonal weight matrix. The typical use case
    is for modeling correlations among outputs of a multi-output GP, where
    outputs are coded as distinct data points with one-hot coded features
    denoting which output each datapoint represents.

    If only ``rank`` is specified, the kernel ``(C C^T + D)`` will be
    randomly initialized to a matrix with expected value the identity matrix.

    References:

    [1] Mauricio A. Alvarez, Lorenzo Rosasco, Neil D. Lawrence (2012)
        Kernels for Vector-Valued Functions: a Review

    :param int input_dim: Number of feature dimensions of inputs.
    :param int rank: Optional rank. This is only used if ``components`` is
        unspecified. If neigher ``rank`` nor ``components`` is specified,
        then ``rank`` defaults to ``input_dim``.
    :param torch.Tensor components: An optional ``(input_dim, rank)`` shaped
        matrix that maps features to ``rank``-many components. If unspecified,
        this will be randomly initialized.
    :param torch.Tensor diagonal: An optional vector of length ``input_dim``.
        If unspecified, this will be set to constant ``1 - rank / input_dim`` if
        ``rank < input_dim`` otherwise zero.
    :param list active_dims: List of feature dimensions of the input which the
        kernel acts on.
    :param str name: Name of the kernel.
    """

    def __init__(self, input_dim, rank=None, components=None, diagonal=None, active_dims=None, name="coregionalize"):
        super(Coregionalize, self).__init__(input_dim, active_dims, name)

        # Add a low-rank kernel with expected value torch.eye(input_dim, input_dim) * rank / input_dim.
        if components is None:
            rank = input_dim if rank is None else rank
            components = torch.randn(input_dim, rank) / input_dim ** 0.5
        else:
            rank = components.shape[-1]
        if components.shape != (input_dim, rank):
            raise ValueError("Expected components.shape == ({},rank), actual {}".format(input_dim, components.shape))
        self.components = Parameter(components)

        # Add a diagonal component only if rank < input_dim.
        # The expected value should be torch.eye(input_dim, input_dim) * (1 - rank / input_dim),
        # such that the result has expected value the identity matrix.
        if diagonal is None and rank < input_dim:
            diagonal = components.new_ones(input_dim) * (1.0 - rank / input_dim)
        if diagonal is None:
            self.diagonal = None
        else:
            if diagonal.shape != (input_dim,):
                raise ValueError("Expected diagonal.shape == ({},), actual {}".format(input_dim, diagonal.shape))
            self.diagonal = Parameter(diagonal)
            self.set_constraint("diagonal", constraints.positive)

    def forward(self, X, Z=None, diag=False):
        components = self.get_param("components")
        diagonal = None if self.diagonal is None else self.get_param("diagonal")
        X = self._slice_input(X)
        Xc = X.matmul(components)

        if diag:
            result = (Xc ** 2).sum(-1)
            if diagonal is not None:
                result = result + (X ** 2).mv(diagonal)
            return result

        if Z is None:
            Z = X
            Zc = Xc
        else:
            Z = self._slice_input(Z)
            Zc = Z.matmul(components)

        result = Xc.matmul(Zc.t())
        if diagonal is not None:
            result = result + (X * diagonal).matmul(Z.t())
        return result
