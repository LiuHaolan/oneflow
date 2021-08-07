"""
Copyright 2020 The OneFlow Authors. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import oneflow
import oneflow.fx
from oneflow.fx.node import Node, map_aggregate
from typing import Any, Tuple, NamedTuple, Optional


class TensorMetadata(NamedTuple):
    # TensorMetadata is a structure containing pertinent information
    # about a tensor within a PyTorch program.

    # General Tensor metadata
    shape: oneflow.Size
    dtype: oneflow.dtype
    requires_grad: bool
    stride: Tuple[int]
    memory_format: Optional[oneflow.memory_format]

    # Quantization metadata
    is_quantized: bool
    qscheme: Optional[oneflow.qscheme]
    q_scale: Optional[float]
    q_zero_point: Optional[int]


def extract_tensor_metadata(result: oneflow.Tensor) -> TensorMetadata:
    """
    Extract a TensorMetadata NamedTuple describing `result`.
    """
    shape = result.shape
    dtype = result.dtype
    requires_grad = result.requires_grad
    stride = result.stride()

    memory_formats = {
        oneflow.contiguous_format,
        oneflow.channels_last,
        oneflow.channels_last_3d,
    }

    memory_format = None

    for query_format in memory_formats:
        if result.is_contiguous(memory_format=query_format):
            memory_format = query_format
            break

    is_quantized = result.is_quantized
    qscheme = None
    q_scale = None
    q_zero_point = None

    if is_quantized:
        qscheme = result.qscheme()

        if qscheme in {oneflow.per_tensor_affine, oneflow.per_tensor_symmetric}:
            q_scale = result.q_scale()
            q_zero_point = result.q_zero_point()

    return TensorMetadata(
        shape,
        dtype,
        requires_grad,
        stride,
        memory_format,
        is_quantized,
        qscheme,
        q_scale,
        q_zero_point,
    )


class ShapeProp(oneflow.fx.Interpreter):
    """
    Execute an FX graph Node-by-Node and
    record the shape and type of the result
    into the corresponding node.

    Example:
         In this example, we record the shape
         and data type of a module given
         an example input ``oneflow.randn(50, D_in)``.
         We print the name, shape and dtype of each node.

        class TwoLayerNet(oneflow.nn.Module):
            def __init__(self, D_in, H, D_out):
                super(TwoLayerNet, self).__init__()
                self.linear1 = oneflow.nn.Linear(D_in, H)
                self.linear2 = oneflow.nn.Linear(H, D_out)
            def forward(self, x):
                h_relu = self.linear1(x).clamp(min=0)
                y_pred = self.linear2(h_relu)
                return y_pred
        N, D_in, H, D_out = 64, 1000, 100, 10
        x = oneflow.randn(N, D_in)
        y = oneflow.randn(N, D_out)
        model = TwoLayerNet(D_in, H, D_out)
        gm = oneflow.fx.symbolic_trace(model)
        sample_input = oneflow.randn(50, D_in)
        ShapeProp(gm).propagate(sample_input)

        for node in gm.graph.nodes:
            print(node.name, node.dtype, node.shape)

        The output of this code is:

        x oneflow.float32 oneflow.Size([50, 1000])
        linear1 oneflow.float32 oneflow.Size([50, 100])
        clamp_1 oneflow.float32 oneflow.Size([50, 100])
        linear2 oneflow.float32 oneflow.Size([50, 10])
        output oneflow.float32 oneflow.Size([50, 10])

    Args:
         module (GraphModule): The module to be executed

    """

    def run_node(self, n: Node) -> Any:
        result = super().run_node(n)

        found_tensor = False

        def extract_tensor_meta(obj):
            if isinstance(obj, oneflow.Tensor):
                nonlocal found_tensor
                found_tensor = True
                return extract_tensor_metadata(obj)
            else:
                return obj

        meta = map_aggregate(result, extract_tensor_meta)
        if found_tensor:
            n.meta["tensor_meta"] = meta

        n.meta["type"] = type(result)
        return result

    def propagate(self, *args):
        """
        Run `module` via interpretation and return the result and
        record the shape and type of each node.

        Args:
            *args (Tensor): the sample input.

        Returns:
            Any: The value returned from executing the Module
        """
        return super().run(*args)