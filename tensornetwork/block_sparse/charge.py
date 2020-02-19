# Copyright 2019 The TensorNetwork Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import numpy as np

# pylint: disable=line-too-long
from typing import List, Optional, Type, Any, Union


class BaseCharge:
  """
  Base class for charges of BlockSparseTensor. All user defined charges 
  should be derived from this class.
  Attributes:
    * unique_charges: np.ndarray of shape `(m,n)` with `m`
      the number of charge types, and `n` the number of unique charges.
    * charge_labels: np.ndarray of dtype np.int16. Used for identifying 
      charges with integer labels. `unique_charges[:, charge_labels] 
      is the np.ndarray of actual charges.
    * charge_types: A list of `type` objects. Stored the different charge types,
      on for each row in `unique_charges`.
      
  """

  def __init__(self,
               charges: np.ndarray,
               charge_labels: Optional[np.ndarray] = None,
               charge_types: Optional[List[Type["BaseCharge"]]] = None) -> None:
    self.charge_types = charge_types
    if charges.ndim == 1:
      charges = np.expand_dims(charges, 0)
    if charge_labels is None:
      self.unique_charges, self.charge_labels = np.unique(
          charges.astype(np.int16), return_inverse=True, axis=1)
      self.charge_labels = self.charge_labels.astype(np.int16)
    else:
      self.charge_labels = np.asarray(charge_labels, dtype=np.int16)

      self.unique_charges = charges.astype(np.int16)
      self.charge_labels = charge_labels.astype(np.int16)

  @staticmethod
  def fuse(charge1, charge2):
    raise NotImplementedError("`fuse` has to be implemented in derived classes")

  @staticmethod
  def dual_charges(charges):
    raise NotImplementedError(
        "`dual_charges` has to be implemented in derived classes")

  @staticmethod
  def identity_charge():
    raise NotImplementedError(
        "`identity_charge` has to be implemented in derived classes")

  @classmethod
  def random(cls, minval: int, maxval: int, dimension: int):
    raise NotImplementedError(
        "`random` has to be implemented in derived classes")

  @property
  def dim(self):
    return len(self.charge_labels)

  @property
  def num_symmetries(self) -> int:
    """
    Return the number of different charges in `ChargeCollection`.
    """
    return self.unique_charges.shape[0]

  @property
  def num_unique(self) -> int:
    """
    Return the number of different charges in `ChargeCollection`.
    """
    return self.unique_charges.shape[1]

  def copy(self):
    """
    Return a copy of `BaseCharge`.
    """
    obj = self.__new__(type(self))
    obj.__init__(
        charges=self.unique_charges.copy(),
        charge_labels=self.charge_labels.copy(),
        charge_types=self.charge_types)
    return obj

  @property
  def charges(self):
    """
    Return the actual charges of `BaseCharge` as np.ndarray.
    """
    return self.unique_charges[:, self.charge_labels]

  def __repr__(self):
    return str(
        type(self)) + '\n' + 'charges: \n' + self.charges.__repr__() + '\n'

  def __len__(self):
    return len(self.charge_labels)

  def __eq__(self,
             target_charges: Union[np.ndarray, "BaseCharge"]) -> np.ndarray:
    if isinstance(target_charges, type(self)):
      targets = np.unique(
          target_charges.unique_charges[:, target_charges.charge_labels],
          axis=1)
    else:
      if target_charges.ndim == 1:
        target_charges = np.expand_dims(target_charges, 0)
      targets = np.unique(target_charges, axis=1)
    #pylint: disable=no-member
    inds = np.nonzero(
        np.logical_and.reduce(
            np.expand_dims(self.unique_charges,
                           2) == np.expand_dims(targets, 1),
            axis=0))[0]
    return np.expand_dims(self.charge_labels, 1) == np.expand_dims(inds, 0)

  @property
  def identity_charges(self) -> "BaseCharge":
    """
    Returns the identity charge.
    Returns:
      BaseCharge: The identity charge.
    """
    unique_charges = np.expand_dims(
        np.asarray([ct.identity_charge() for ct in self.charge_types],
                   dtype=np.int16), 1)
    charge_labels = np.zeros(1, dtype=np.int16)
    obj = self.__new__(type(self))
    obj.__init__(unique_charges, charge_labels, self.charge_types)
    return obj

  def __add__(self, other: "BaseCharge") -> "BaseCharge":
    """
    Fuse `self` with `other`.
    Args:
      other: A `BaseCharge` object.
    Returns:
      BaseCharge: The result of fusing `self` with `other`.
    """

    # fuse the unique charges from each index, then compute new unique charges
    comb_charges = fuse_ndarray_charges(self.unique_charges,
                                        other.unique_charges, self.charge_types)
    unique_charges, charge_labels = np.unique(
        comb_charges, return_inverse=True, axis=1)
    charge_labels = charge_labels.reshape(self.unique_charges.shape[1],
                                          other.unique_charges.shape[1]).astype(
                                              np.int16)

    # find new labels using broadcasting
    left_labels = self.charge_labels[:, None] + np.zeros([1, len(other)],
                                                         dtype=np.int16)
    right_labels = other.charge_labels[None, :] + np.zeros([len(self), 1],
                                                           dtype=np.int16)
    charge_labels = charge_labels[np.ravel(left_labels), np.ravel(right_labels)]

    obj = self.__new__(type(self))
    obj.__init__(unique_charges, charge_labels, self.charge_types)

    return obj

  def dual(self, take_dual: Optional[bool] = False) -> "BaseCharge":
    """
    Return the charges of `BaseCharge`, possibly conjugated.
    Args:
      take_dual: If `True` return the dual charges. If `False` return 
        regular charges.
    Returns:
      BaseCharge
    """
    if take_dual:
      unique_dual_charges = np.stack([
          self.charge_types[n].dual_charges(self.unique_charges[n, :])
          for n in range(len(self.charge_types))
      ],
                                     axis=0)

      obj = self.__new__(type(self))
      obj.__init__(unique_dual_charges, self.charge_labels, self.charge_types)
      return obj
    return self

  def __matmul__(self, other):
    #some checks
    if len(self) != len(other):
      raise ValueError(
          '__matmul__ requires charges to have the same number of elements')
    charges = np.concatenate([self.charges, other.charges], axis=0)
    charge_types = self.charge_types + other.charge_types
    return BaseCharge(
        charges=charges, charge_labels=None, charge_types=charge_types)

  def __mul__(self, number: bool) -> "BaseCharge":
    if not isinstance(number, (bool, np.bool_)):
      raise ValueError(
          "can only multiply by `True` or `False`, found {}".format(number))
    return self.dual(number)


class U1Charge(BaseCharge):

  def __init__(self,
               charges: np.ndarray,
               charge_labels: Optional[np.ndarray] = None,
               charge_types: Optional[List[Type["BaseCharge"]]] = None) -> None:
    super().__init__(charges, charge_labels, charge_types=[type(self)])

  @staticmethod
  def fuse(charge1, charge2) -> np.ndarray:
    return np.add.outer(charge1, charge2).ravel()

  @staticmethod
  def dual_charges(charges) -> np.ndarray:
    return charges * charges.dtype.type(-1)

  @staticmethod
  def identity_charge() -> np.ndarray:
    return np.int16(0)

  @classmethod
  def random(cls, minval: int, maxval: int, dimension: int) -> np.ndarray:
    charges = np.random.randint(minval, maxval, dimension, dtype=np.int16)
    return cls(charges=charges)


def fuse_ndarray_charges(charges_A: np.ndarray, charges_B: np.ndarray,
                         charge_types: List[Type[BaseCharge]]) -> np.ndarray:
  """
  Fuse the quantum numbers of two indices under their kronecker addition.
  Args:
    charges_A (np.ndarray): n-by-D1 dimensional array integers encoding charges,
      with n the number of symmetries and D1 the index dimension.
    charges__B (np.ndarray): n-by-D2 dimensional array of charges.
    charge_types: A list of types of the charges.
  Returns:
    np.ndarray: n-by-(D1 * D2) dimensional array of the fused charges.
  """
  comb_charges = [0] * len(charge_types)
  for n, ct in enumerate(charge_types):
    comb_charges[n] = ct.fuse(charges_A[n, :], charges_B[n, :])

  return np.concatenate(
      comb_charges, axis=0).reshape(
          len(charge_types), charges_A.shape[1] * charges_B.shape[1])


def intersect(A: np.ndarray,
              B: np.ndarray,
              axis=0,
              assume_unique=False,
              return_indices=False) -> Any:
  """
  Extends numpy's intersect1d to find the row or column-wise intersection of
  two 2d arrays. Takes identical input to numpy intersect1d.
  Args:
    A, B (np.ndarray): arrays of matching widths and datatypes
  Returns:
    ndarray: sorted 1D array of common rows/cols between the input arrays
    ndarray: the indices of the first occurrences of the common values in A.
      Only provided if return_indices is True.
    ndarray: the indices of the first occurrences of the common values in B.
      Only provided if return_indices is True.
  """
  #see https://stackoverflow.com/questions/8317022/get-intersecting-rows-across-two-2d-numpy-arrays
  #pylint: disable=no-else-return
  if A.ndim == 1:
    return np.intersect1d(
        A, B, assume_unique=assume_unique, return_indices=return_indices)

  elif A.ndim == 2:
    if axis == 0:
      ncols = A.shape[1]
      if A.shape[1] != B.shape[1]:
        raise ValueError("array widths must match to intersect")

      dtype = {
          'names': ['f{}'.format(i) for i in range(ncols)],
          'formats': ncols * [A.dtype]
      }
      if return_indices:
        C, A_locs, B_locs = np.intersect1d(
            A.view(dtype),
            B.view(dtype),
            assume_unique=assume_unique,
            return_indices=return_indices)
        return C.view(A.dtype).reshape(-1, ncols), A_locs, B_locs
      C = np.intersect1d(
          A.view(dtype), B.view(dtype), assume_unique=assume_unique)
      return C.view(A.dtype).reshape(-1, ncols)

    elif axis == 1:
      #@Glen: why the copy here?
      out = intersect(
          A.T.copy(),
          B.T.copy(),
          axis=0,
          assume_unique=assume_unique,
          return_indices=return_indices)
      if return_indices:
        return out[0].T, out[1], out[2]
      return out.T

    raise NotImplementedError(
        "intersection can only be performed on first or second axis")

  raise NotImplementedError("intersect is only implemented for 1d or 2d arrays")


def fuse_charges(charges: List[BaseCharge], flows: List[bool]) -> BaseCharge:
  """
  Fuse all `charges` into a new charge.
  Charges are fused from "right to left",
  in accordance with row-major order.

  Args:
    charges: A list of charges to be fused.
    flows: A list of flows, one for each element in `charges`.
  Returns:
    BaseCharge: The result of fusing `charges`.
  """
  if len(charges) != len(flows):
    raise ValueError(
        "`charges` and `flows` are of unequal lengths {} != {}".format(
            len(charges), len(flows)))
  fused_charges = charges[0] * flows[0]
  for n in range(1, len(charges)):
    fused_charges = fused_charges + charges[n] * flows[n]
  return fused_charges


def fuse_degeneracies(degen1: Union[List, np.ndarray],
                      degen2: Union[List, np.ndarray]) -> np.ndarray:
  """
  Fuse degeneracies `degen1` and `degen2` of two leg-charges
  by simple kronecker product. `degen1` and `degen2` typically belong to two
  consecutive legs of `BlockSparseTensor`.
  Given `degen1 = [1, 2, 3]` and `degen2 = [10, 100]`, this returns
  `[10, 100, 20, 200, 30, 300]`.
  When using row-major ordering of indices in `BlockSparseTensor`,
  the position of `degen1` should be "to the left" of the position of `degen2`.
  Args:
    degen1: Iterable of integers
    degen2: Iterable of integers
  Returns:
    np.ndarray: The result of fusing `dege1` with `degen2`.
  """
  return np.reshape(
      np.expand_dims(degen1, 1) * np.expand_dims(degen2, 0),
      len(degen1) * len(degen2))


def fuse_ndarrays(arrays: List[Union[List, np.ndarray]]) -> np.ndarray:
  """
  Fuse all `arrays` by simple kronecker addition.
  Arrays are fused from "right to left", 
  Args:
    arrays: A list of arrays to be fused.
  Returns:
    np.ndarray: The result of fusing `arrays`.
  """
  if len(arrays) == 1:
    return np.array(arrays[0])
  fused_arrays = np.asarray(arrays[0])
  for n in range(1, len(arrays)):
    fused_arrays = np.ravel(np.add.outer(fused_arrays, arrays[n]))
  return fused_arrays