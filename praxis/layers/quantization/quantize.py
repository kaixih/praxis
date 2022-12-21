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

"""Rewriter decorator(s) for quantizing models.

Those functions help creating quantized models/params for pax system.

Example usage:

class XYZModel():
  ...

@for_transformer()
class QuantizedXYZModel(XYZModel):
  pass

This creates a quantized model for the original XYZModel configuration by
quantizing all transformer blocks.

"""

import functools
from typing import cast, Type
import fiddle as fdl
from praxis import base_layer
from praxis import layers
from praxis import pax_fiddle
from praxis.layers import quantization
from praxis.layers.quantization import quantization_hparams

LayerTpl = pax_fiddle.Config[base_layer.BaseLayer]


# TODO(jianlijianli): mark quantize_* as private.
def quantize_transformer_layer_weights(
    tr_tpl: pax_fiddle.Config[layers.transformers.Transformer],
    quantization_type: quantization_hparams.QuantizationType,
    mode: quantization_hparams.QuantizationMode,
) -> None:
  """Rewrites Transformer HParam for weight only quantization."""

  tr_atten_tpl = cast(
      pax_fiddle.Config[layers.attentions.DotProductAttention],
      tr_tpl.tr_atten_tpl,
  )
  tr_fflayer_tpl = cast(
      pax_fiddle.Config[layers.transformers.TransformerFeedForward],
      tr_tpl.tr_fflayer_tpl,
  )
  quantize_dot_product_attention_layer_weights(tr_atten_tpl, quantization_type,
                                               mode)
  quantize_transformer_feed_forward_layer_weights(tr_fflayer_tpl,
                                                  quantization_type, mode)


def quantize_dot_product_attention_layer_weights(
    attn_tpl: pax_fiddle.Config[layers.attentions.DotProductAttention],
    quantization_type: quantization_hparams.QuantizationType,
    mode: quantization_hparams.QuantizationMode,
) -> None:
  """Rewrites DotProductAttention HParam for weight only quantization."""

  attn_tpl.proj_tpl = pax_fiddle.Config(
      quantization.AttentionProjection,
      quantization=quantization_hparams.QuantizationHParams(
          quantization_type=quantization_type, mode=mode
      ),
  )

  if attn_tpl.combine_qkv:
    attn_tpl.combined_qkv_proj_tpl = pax_fiddle.Config(
        quantization.attentions.CombinedQKVProjectionLayer,
        quantization=quantization_hparams.QuantizationHParams(
            quantization_type=quantization_type, mode=mode
        ),
    )


def quantize_transformer_feed_forward_layer_weights(
    tr_fflayer_tpl: pax_fiddle.Config[
        layers.transformers.TransformerFeedForward
    ],
    quantization_type: quantization_hparams.QuantizationType,
    mode: quantization_hparams.QuantizationMode,
) -> None:
  """Rewrites TransformerFeedForward HParam for weight only quantization."""

  tr_fflayer_tpl.fflayer_tpl.linear_tpl = pax_fiddle.Config(
      quantization.Linear,
      quantization=quantization_hparams.QuantizationHParams(
          quantization_type=quantization_type, mode=mode
      ),
  )


# TODO(jianlijianli): Add decorator for other model architectures.
# Ready-to-use quantization decorators for quantizing transformer.
def for_transformer():
  """Find and quantize transformer.

  If there are transformers that shouldn't be quantized, use lowers level APIs
  and manually/selectively quantize the model.

  If there are no transformers in the model, it's a no-op.

  TODO(jianlijianli): pass in additional parameters.

  Returns:
    a modifier that quantizes transformers when applied to a config.
  """

  def decorator(cls):
    """decorator that quantize transformers."""

    @functools.wraps(cls, updated=())  # to keep original class name.
    class Wrapper(cls):
      """Wrapper class for cls with Quantization enabled."""

      def task(self):
        config = super(Wrapper, self)
        task_p = config.task()
        mode = quantization_hparams.QuantizationMode.TRAINING
        quantization_type = quantization_hparams.QuantizationType.FQ
        set_quantization(
            task_p.model,
            layers.transformers.Transformer,
            quantization_type=quantization_type,
            mode=mode,
        )
        return task_p

    return Wrapper

  return decorator


def set_quantization(config: LayerTpl, target: Type[base_layer.BaseLayer],
                     quantization_type: quantization_hparams.QuantizationType,
                     mode: quantization_hparams.QuantizationMode):
  target_tpls = find_target_tpl(config, target)
  for target_tpl in target_tpls:
    quantize_transformer_layer_weights(target_tpl, quantization_type, mode)  # pytype: disable=wrong-arg-types  # py310-upgrade


# Traverse entire config HParam and find the tpl of the target type.
def find_target_tpl(config: LayerTpl, target: Type[base_layer.BaseLayer]):
  """Find and return target tpl from the config."""
  to_process = [config]
  target_tpl = []
  while to_process:
    param = to_process.pop(0)
    if isinstance(param, fdl.Config):
      if issubclass(fdl.get_callable(param), target):
        target_tpl.append(param)
        continue
      else:
        to_process.extend(fdl.ordered_arguments(param).values())
  return target_tpl
