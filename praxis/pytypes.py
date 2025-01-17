# coding=utf-8
# Copyright 2022 The Pax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Common pytype definitions."""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, Union

import clu.metrics as clu_metrics
import jax
from jax import core
from jax import numpy as jnp
from jaxtyping import AbstractDtype, Bool, Float, Int, Float32, Int32, PyTree, Shaped, jaxtyped  # pylint: disable=g-multiple-import, g-importing-member, unused-import
import numpy as np
from praxis import lingvo_lib

# No other imports from lingvo should be accessed by core JAX library.
InstantiableParams = lingvo_lib.InstantiableParams
NestedMap = lingvo_lib.NestedMap
HParams = lingvo_lib.HParams
HParamsT = HParams

JTensor = jnp.ndarray
PRNGKey = JTensor
JTensorOrPartitionSpec = Union[JTensor, jax.sharding.PartitionSpec]
NpTensor = np.ndarray
SummaryDict = Union[NestedMap, Dict[str, JTensor]]
PyTree = Any
PyTreeDef = jax.tree_util.PyTreeDef


T = TypeVar('T')
Nested = Union[T, Tuple[Any, ...], List[Any], Dict[str, Any], NestedMap]
NestedJTensor = Nested[JTensor]
NestedNpTensor = Nested[NpTensor]
NestedBool = Nested[bool]
NestedInt = Nested[int]
NestedHParams = Nested[HParamsT]
NestedPartitionSpec = Nested[jax.sharding.PartitionSpec]
NestedJTensorOrPartitionSpec = Nested[JTensorOrPartitionSpec]
NestedShapeDtypeStruct = Nested[jax.ShapeDtypeStruct]
NestedShapedArray = Nested[core.ShapedArray]
NestedShapeDtypeLike = Union[
    NestedJTensor, NestedNpTensor, NestedShapeDtypeStruct, NestedShapedArray
]

# Sharding annotation for a dim can be a single int, or a str, or a sequence of
# (int, str), or None. For example "1", "-1", "None", "data", "(data, replica)"
# are all valid sharding annotations for a particular tensor axis.
DimShardingAnnotation = Optional[Union[Sequence[Union[int, str]], int, str]]
SplitDimsMapping = Optional[Sequence[DimShardingAnnotation]]

# Note(b/238657605): pytypes Metrics were renamed to WeightedScalars
# and Metrics are now true metric objects using clu.metrics
WeightedScalar = Tuple[JTensor, JTensor]
WeightedScalars = Union[Dict[str, WeightedScalar], NestedMap]
WeightedScalarsList = Union[Dict[str, Sequence[WeightedScalar]], NestedMap]
Metrics = Union[NestedMap, Dict[str, clu_metrics.Metric]]

LogicalAxisRules = Sequence[Tuple[str, Optional[str]]]

DotGeneralT = Callable[..., jnp.ndarray]


# jaxtyping utils.
class _MetaArrayT(type):
  types = ()

  def __instancecheck__(cls, obj):
    return isinstance(obj, cls.types)


class JaxArrayT(metaclass=_MetaArrayT):
  types = (jax.Array, jax.ShapeDtypeStruct)


class ArrayT(metaclass=_MetaArrayT):
  types = (JaxArrayT, np.ndarray)
