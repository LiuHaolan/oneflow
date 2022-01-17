/*
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
*/
#include "oneflow/core/vm/release_tensor_arg_phy_instr_operand.h"
#include "oneflow/core/eager/local_dep_object.h"
#include "oneflow/core/eager/eager_blob_object.h"

namespace oneflow {

namespace vm {

void ReleaseTensorArgPhyInstrOperand::ForEachConstMirroredObject(
    const std::function<void(MirroredObject* infer, MirroredObject* compute)>& DoEach) const {
  // Do nothing
}

void ReleaseTensorArgPhyInstrOperand::ForEachMutMirroredObject(
    const std::function<void(MirroredObject* infer, MirroredObject* compute)>& DoEach) const {
  if (eager_blob_object_->producer_op_device().has_value()) {
    DoEach(nullptr, CHECK_JUST(eager_blob_object_->producer_op_device())
                        ->mut_schedule_local_dep_object()
                        ->mut_mirrored_object());
  }
  DoEach(nullptr, compute_local_dep_object_->mut_mirrored_object());
}

void ReleaseTensorArgPhyInstrOperand::ForEachMut2MirroredObject(
    const std::function<void(MirroredObject* infer, MirroredObject* compute)>& DoEach) const {
  // Do nothing
}

}  // namespace vm
}  // namespace oneflow