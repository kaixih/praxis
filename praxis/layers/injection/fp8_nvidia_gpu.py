# coding=utf-8
# Copyright 2023 The Pax Authors.
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

"""Op wrappers to support FP8 GEMMs."""

from functools import partial

from flax.linen import fp8_ops

from jax import custom_vjp
from jax import lax
from jax import numpy as jnp

from praxis import base_layer
from praxis import layers
from praxis import pax_fiddle
from praxis import pytypes

WeightInit = base_layer.WeightInit
WeightHParams = base_layer.WeightHParams
JTensor = pytypes.JTensor
OVERWRITE_WITH_GRADIENT = \
    base_layer.WeightHParamsCollection.OVERWRITE_WITH_GRADIENT


def fp8_einsum(eqn, x, k, compute_dtype, x_scale, x_amax_history, k_scale,
               k_amax_history, dy_scale, dy_amax_history):
  """Perform any einsum formula.  """

  x_qdq = fp8_ops.in_qdq(compute_dtype, x, x_scale, x_amax_history)

  k_qdq = fp8_ops.in_qdq(compute_dtype, k, k_scale, k_amax_history)

  y_qdq = jnp.einsum(eqn, x_qdq, k_qdq)

  y = fp8_ops.out_qdq(compute_dtype, y_qdq, dy_scale, dy_amax_history)

  return y


class Fp8EinsumOp(base_layer.BaseLayer):
  """Wrapper around jnp.einsum used in standard Pax layers."""
  amax_history_length: int = 1024

  def setup(self) -> None:
    scale_args = {
        'shape': [1],
        'init': WeightInit.Constant(1.0),
        'dtype': jnp.float32,
        'mesh_shape': self.mesh_shape,
        'tensor_split_dims_mapping': None,
        'collections': [OVERWRITE_WITH_GRADIENT],
    }
    amax_history_args = {
        'shape': [self.amax_history_length],
        'init': WeightInit.Constant(0.0),
        'dtype': jnp.float32,
        'mesh_shape': self.mesh_shape,
        'tensor_split_dims_mapping': None,
        'collections': [OVERWRITE_WITH_GRADIENT],
    }
    self.create_variable(
        'input_amax_history', WeightHParams(**amax_history_args))
    self.create_variable(
        'kernel_amax_history', WeightHParams(**amax_history_args))
    self.create_variable(
        'output_grad_amax_history', WeightHParams(**amax_history_args))

    self.create_variable('input_scale', WeightHParams(**scale_args))
    self.create_variable('kernel_scale', WeightHParams(**scale_args))
    self.create_variable(
         'output_grad_scale', WeightHParams(**scale_args))

  def __call__(self, equation: str, *args: JTensor) -> JTensor:

    assert len(args) == 2
    x = args[0]
    k = args[1]

    comp_dtype = self.fprop_dtype
    assert (
        k.dtype == comp_dtype
    ), f'k dtype has to be {comp_dtype}, but got {k.dtype}'
    x = jnp.asarray(x, comp_dtype)

    theta = self.theta
    out = fp8_einsum(equation, x, k, comp_dtype, theta.input_scale,
                     theta.input_amax_history, theta.kernel_scale,
                     theta.kernel_amax_history, theta.output_grad_scale,
                     theta.output_grad_amax_history)
    return out


def tr_set_fp8_quantization(
    transformer_layer_p: pax_fiddle.Config[layers.transformers.Transformer]
):
  """Inject Fp8EinsumOp to desired layers in transformer."""
  transformer_layer_p.tr_atten_tpl.proj_tpl.einsum_tpl = \
      pax_fiddle.Config(Fp8EinsumOp)
  transformer_layer_p.tr_atten_tpl.combined_qkv_proj_tpl.einsum_tpl = \
      pax_fiddle.Config(Fp8EinsumOp)
  transformer_layer_p.tr_fflayer_tpl.fflayer_tpl.linear_tpl.einsum_tpl = \
      pax_fiddle.Config(Fp8EinsumOp)
