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
import uuid


def exec(f):
    def wrapper(*args, **kwargs):
        m = args[0]
        assert isinstance(m, oneflow.nn.Module)
        for arg in args[1::]:
            print(id(arg))
            isinstance(arg, oneflow._oneflow_internal.Tensor)
        func_name = str(uuid.uuid4()).replace("-", "")
        func_name = f"jit{func_name}"
        print([(k, v.dtype, v.shape) for k, v in m.named_parameters()])
        assert oneflow._oneflow_internal.ir.toggle_jit(func_name)
        oneflow._oneflow_internal.ir.set_jit_forward_args(
            args[1::], list(m.parameters())
        )
        # NOTE: forbid calling __repr__ in the forward function
        result = f(*args, **kwargs)
        assert not oneflow._oneflow_internal.ir.toggle_jit(func_name)
        return result

    return wrapper