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
#include "oneflow/core/eager/local_dep_object.h"
#include "oneflow/core/common/decorator.h"
#include "oneflow/core/common/static_global.h"

namespace oneflow {

intrusive::shared_ptr<LocalDepObject> NewLocalDepObject() {
  return intrusive::make_shared<LocalDepObject>();
}

namespace {

intrusive::shared_ptr<LocalDepObject> RawGetLocalDepObject4Device(const Device& device) {
  return NewLocalDepObject();
}

}  // namespace

LocalDepObject* GetStaticLocalDepObject4Device(const Device& device) {
  static constexpr auto* GetDep = DECORATE(&RawGetLocalDepObject4Device, StaticGlobalCopiable);
  return GetDep(device).Mutable();
}

}  // namespace oneflow
