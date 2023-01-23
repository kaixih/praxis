# coding=utf-8
# Copyright 2022 Google LLC.
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

"""Quantized Multi-Query Attention layers."""

from typing import Any

from jax import numpy as jnp
from praxis import base_layer
from praxis import pytypes
from praxis.layers import multi_query_attention
from praxis.layers.quantization import operations
from praxis.layers.quantization import quantization_hparams

WeightInit = base_layer.WeightInit
QuantizationMode = quantization_hparams.QuantizationMode
QuantizationType = quantization_hparams.QuantizationType
QuantizationHParams = quantization_hparams.QuantizationHParams
WeightHParams = base_layer.WeightHParams
sub_config_field = base_layer.sub_config_field
JTensor = pytypes.JTensor


class OneHeadedAttentionProjection(
    multi_query_attention.OneHeadedAttentionProjection
):
  """Quantized OneHeadedAttentionProjection.

  Attributes:
    quantization: Information related to the quantization applied to this layer,
      such as the mode for the quantization.
  """

  quantization: QuantizationHParams = sub_config_field(QuantizationHParams)

  def setup(self) -> None:
    wp = self.weight_split_dims_mapping
    if self.mesh_shape is not None:
      assert wp.wt is not None, ('Must provide sharding annotations for the '
                                 'weights if mesh shape is provided')
    wt = wp.wt
    pc_shape = [self.input_dim, self.output_dim]
    pc = WeightHParams(
        shape=pc_shape, mesh_shape=self.mesh_shape, tensor_split_dims_mapping=wt
    )
    if self.quantization.mode == QuantizationMode.INFERENCE:
      self.create_quantized_variable('w', pc, [self.output_dim])
    else:
      self.create_variable('w', pc)
    if self.use_bias:
      if self.mesh_shape is not None:
        bias_split_dims_mapping = [wp.wt[1]]
      else:
        bias_split_dims_mapping = None
      pc_bias = WeightHParams(
          shape=[self.output_dim],
          init=WeightInit.Constant(0.0),
          mesh_shape=self.mesh_shape,
          tensor_split_dims_mapping=bias_split_dims_mapping,
      )
      self.create_variable('b', pc_bias)

  def __call__(self, inputs: JTensor) -> JTensor:
    """Computes the multi headed projection for inputs.

    Args:
      inputs: A JTensor of shape [..., p.input_dim].

    Returns:
      The projected JTensor with shape [..., p.output_dim].
    """
    theta = self.theta

    shape = inputs.shape
    inputs = self._cast_to_fprop_dtype(inputs)

    assert (
        shape[-1] == self.input_dim
    ), f'Expecting shape[-1] == p.input_dim, {shape[-1]} != {self.input_dim}'
    eqn = '...D,DH->...H'
    if self.quantization.mode == QuantizationMode.INFERENCE:
      w, s = self.get_quantized_weight('w')
      ret = operations.einsum(eqn, inputs, w, s)
    else:
      w = theta.w
      ret = jnp.einsum(eqn, inputs, w)
    if self.use_bias:
      ret += theta.b
    return ret

  def quantized_partitioned_specs(self) -> Any:
    """Get quantized PartitionSpec.

    Returns:
      a map from names to partition spec.
    """
    scale_name = 'w' + base_layer.QUANTIZED_NAME_POSTFIX
    weight_pspec = base_layer._weight_hparam_to_pspec(
        self._weight_hparams['w'], self.mesh_axis_names
    )
    wp = self.weight_split_dims_mapping
    scale_split_dims_mapping = [wp.wt[1]]
    # scale_weight_hparam is unmaterialized so shape is irrelevant.
    scale_weight_hparam = WeightHParams(
        shape=(), tensor_split_dims_mapping=scale_split_dims_mapping
    )
    scale_pspec = base_layer._weight_hparam_to_pspec(
        scale_weight_hparam, self.mesh_axis_names
    )
    partitionspec = {'w': weight_pspec, scale_name: scale_pspec}

    # Activation variable partitioning is only needed for static quantization.
    if self._do_static_activation_quantization():
      raise NotImplementedError(
          'Static activation quantization is not supported yet.'
      )

    return {base_layer.PARAMS: partitionspec}

  def quantize_weight(self) -> JTensor:
    """Get quantized weight.

    Returns:
      a map from names to quantized weights.
    """
    theta = self.theta
    scale_name = 'w' + base_layer.QUANTIZED_NAME_POSTFIX
    eqn = 'xy,yz->xz'
    bits = self.quantization.weight_params.precision
    percentile = self.quantization.weight_params.clipping_coeff
    if self.quantization.quantization_type == QuantizationType.PTQ:
      if self._do_static_activation_quantization():
        raise NotImplementedError(
            'Static activation quantization is not supported yet.'
        )
      else:
        q_w, q_s = operations.reduce_einsum_weight_precision(
            eqn,
            theta.w,
            calculation_type=self.dtype,
            bits=bits,
            percentile=percentile,
        )
        return {base_layer.PARAMS: {'w': q_w, scale_name: q_s}}
    else:
      raise NotImplementedError(
          'Only PTQ is supported in quantized multi_query_attention.'
      )