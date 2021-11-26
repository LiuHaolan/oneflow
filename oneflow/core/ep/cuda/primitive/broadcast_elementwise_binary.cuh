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
#include "oneflow/core/ep/include/primitive//broadcast_elementwise_binary.h"
#include "oneflow/core/ep/common/primitive/broadcast_elementwise_binary.h"
#include "oneflow/core/ep/cuda/primitive/type_seq.h"
#include "oneflow/core/ep/cuda/cuda_stream.h"
#include "oneflow/core/cuda/elementwise.cuh"
#include "oneflow/core/ep/cuda/primitive/binary_functor.cuh"

namespace oneflow {

namespace ep {
namespace primitive {

template<BinaryOp binary_op, typename Src, typename Dst, size_t num_dims, size_t src0_pack_size,
         size_t src1_pack_size, typename IndexType>
__global__ void BroadcastElementwiseBinaryGpu(
    BroadcastElementwiseBinaryParams<num_dims, IndexType> params) {
  constexpr size_t dst_pack_size =
      src0_pack_size > src1_pack_size ? src0_pack_size : src1_pack_size;
  static_assert(src0_pack_size == dst_pack_size || src0_pack_size == 1, "");
  static_assert(src1_pack_size == dst_pack_size || src1_pack_size == 1, "");

  const PackType<Src, src0_pack_size>* src0 =
      reinterpret_cast<const PackType<Src, src0_pack_size>*>(params.src0);
  const PackType<Src, src1_pack_size>* src1 =
      reinterpret_cast<const PackType<Src, src1_pack_size>*>(params.src1);
  PackType<Dst, dst_pack_size>* dst = reinterpret_cast<PackType<Dst, dst_pack_size>*>(params.dst);

  IndexType src0_index[num_dims];
  IndexType src1_index[num_dims];
  IndexType dst_index[num_dims];
  CUDA_1D_KERNEL_LOOP_T(IndexType, offset, params.count) {
    params.dst_index_helper.OffsetToNdIndex(offset, dst_index);
    for (int64_t i = 0; i < num_dims; ++i) {
      if (params.src0_dims[i] == 1) {
        src0_index[i] = 0;
      } else {
        src0_index[i] = dst_index[i];
      }
      if (params.src1_dims[i] == 1) {
        src1_index[i] = 0;
      } else {
        src1_index[i] = dst_index[i];
      }
    }
    const IndexType src0_offset = params.src0_index_helper.NdIndexToOffset(src0_index);
    const IndexType src1_offset = params.src1_index_helper.NdIndexToOffset(src1_index);
    Pack<Src, src0_pack_size> src0_pack;
    src0_pack.storage = src0[src0_offset];
    Pack<Src, src1_pack_size> src1_pack;
    src1_pack.storage = src1[src1_offset];
    Pack<Dst, dst_pack_size> dst_pack;

#pragma unroll
    for (int j = 0; j < dst_pack_size; ++j) {
      const Src src0_val =
          (src0_pack_size == dst_pack_size) ? src0_pack.elem[j] : src0_pack.elem[0];
      const Src src1_val =
          (src1_pack_size == dst_pack_size) ? src1_pack.elem[j] : src1_pack.elem[0];
      dst_pack.elem[j] = BinaryFunctor<DeviceType::kGPU, binary_op, Src, Dst>()(src0_val, src1_val);
    }
    dst[offset] = dst_pack.storage;
  }
}

template<BinaryOp op, typename Src, typename Dst, size_t num_dims, size_t src0_pack_size,
         size_t src1_pack_size, typename IndexType>
void LaunchKernel(Stream* stream, BroadcastElementwiseBinaryParams<num_dims, IndexType> params) {
  auto* cuda_stream = stream->As<CudaStream>();
  BroadcastElementwiseBinaryGpu<op, Src, Dst, num_dims, src0_pack_size, src1_pack_size, IndexType>
      <<<BlocksNum4ThreadsNum(params.count), kCudaThreadsNumPerBlock, 0,
         cuda_stream->cuda_stream()>>>(params);
}

template<BinaryOp binary_op, typename Src, typename Dst>
struct BinaryLhsScalarFunctor {
  __host__ __device__ explicit BinaryLhsScalarFunctor(Src scalar) : scalar(scalar) {}
  __device__ Dst operator()(Src src) const {
    return BinaryFunctor<DeviceType::kGPU, binary_op, Src, Dst>()(scalar, src);
  }
  const Src scalar;
};

template<BinaryOp binary_op, typename Src, typename Dst>
struct BinaryRhsScalarFunctor {
  __host__ __device__ explicit BinaryRhsScalarFunctor(Src scalar) : scalar(scalar) {}
  __device__ Dst operator()(Src src) const {
    return BinaryFunctor<DeviceType::kGPU, binary_op, Src, Dst>()(src, scalar);
  }
  const Src scalar;
};

template<BinaryOp binary_op, typename Src, typename Dst>
struct BinaryLhsScalarPtrFunctorFactory {
  __host__ __device__ explicit BinaryLhsScalarPtrFunctorFactory(const Src* scalar_ptr)
      : scalar_ptr(scalar_ptr) {}
  __device__ BinaryLhsScalarFunctor<binary_op, Src, Dst> operator()() const {
    return BinaryLhsScalarFunctor<binary_op, Src, Dst>(*scalar_ptr);
  }
  const Src* scalar_ptr;
};

template<BinaryOp binary_op, typename Src, typename Dst>
struct BinaryRhsScalarPtrFunctorFactory {
  __host__ __device__ explicit BinaryRhsScalarPtrFunctorFactory(const Src* scalar_ptr)
      : scalar_ptr(scalar_ptr) {}
  __device__ BinaryRhsScalarFunctor<binary_op, Src, Dst> operator()() const {
    return BinaryRhsScalarFunctor<binary_op, Src, Dst>(*scalar_ptr);
  }
  const Src* scalar_ptr;
};

inline bool IsDimsEquals(size_t num_src0_dims, const int64_t* src0_dims, size_t num_src1_dims,
                  const int64_t* src1_dims) {
  if (num_src0_dims != num_src1_dims) { return false; }
  for (size_t i = 0; i < num_src1_dims; ++i) {
    if (src0_dims[i] != src1_dims[i]) { return false; }
  }
  return true;
}

template<BinaryOp binary_op, typename Src, typename Dst>
void DispatchLaunch(Stream* stream, size_t num_src0_dims, const int64_t* src0_dims, const Src* src0,
                    size_t num_src1_dims, const int64_t* src1_dims, const Src* src1, Dst* dst) {
  auto* cuda_stream = stream->As<CudaStream>();
  size_t src0_count = GetElementCount(num_src0_dims, src0_dims);
  size_t src1_count = GetElementCount(num_src1_dims, src1_dims);
  const size_t elem_cnt = std::max(src0_count, src1_count);
  if (IsDimsEquals(num_src0_dims, src0_dims, num_src1_dims, src1_dims)) {
    OF_CUDA_CHECK(
        (cuda::elementwise::Binary(BinaryFunctor<DeviceType::kGPU, binary_op, Src, Dst>(), elem_cnt,
                                   dst, src0, src1, cuda_stream->cuda_stream())));
  } else if (src0_count == 1) {
    OF_CUDA_CHECK((cuda::elementwise::UnaryWithFactory(
        BinaryLhsScalarPtrFunctorFactory<binary_op, Src, Dst>(src0), elem_cnt, dst, src1,
        cuda_stream->cuda_stream())));
  } else if (src1_count == 1) {
    OF_CUDA_CHECK((cuda::elementwise::UnaryWithFactory(
        BinaryRhsScalarPtrFunctorFactory<binary_op, Src, Dst>(src1), elem_cnt, dst, src0,
        cuda_stream->cuda_stream())));
  } else {
    SimplifyThenLaunch<binary_op, Src, Dst>(stream, num_src0_dims, src0_dims, src0, num_src1_dims,
                                            src1_dims, src1, dst);
  }
}

template<typename T>
T GetValue(Scalar value) {
  return value.Value<T>();
}

template<>
half GetValue<half>(Scalar value) {
  return static_cast<half>(GetValue<float>(value));
}

#if CUDA_VERSION >= 11000

template<>
nv_bfloat16 GetValue<nv_bfloat16>(Scalar value) {
  return static_cast<nv_bfloat16>(GetValue<float>(value));
}

#endif  // CUDA_VERSION >= 11000

template<BinaryOp binary_op, typename Src, typename Dst>
class BroadcastElementwiseBinaryImpl : public BroadcastElementwiseBinary {
 public:
  OF_DISALLOW_COPY_AND_MOVE(BroadcastElementwiseBinaryImpl);
  BroadcastElementwiseBinaryImpl() = default;
  ~BroadcastElementwiseBinaryImpl() override = default;

  void Launch(Stream* stream, Scalar src0, size_t num_src1_dims, const int64_t* src1_dims,
              const void* src1, void* dst) override {
    auto* cuda_stream = stream->As<CudaStream>();
    const size_t elem_cnt = GetElementCount(num_src1_dims, src1_dims);
    OF_CUDA_CHECK(
        (cuda::elementwise::Unary(BinaryLhsScalarFunctor<binary_op, Src, Dst>(GetValue<Src>(src0)),
                                  elem_cnt, reinterpret_cast<Dst*>(dst),
                                  reinterpret_cast<const Src*>(src1), cuda_stream->cuda_stream())));
  }
  void Launch(Stream* stream, size_t num_src0_dims, const int64_t* src0_dims, const void* src0,
              Scalar src1, void* dst) override {
    auto* cuda_stream = stream->As<CudaStream>();
    const size_t elem_cnt = GetElementCount(num_src0_dims, src0_dims);
    OF_CUDA_CHECK(
        (cuda::elementwise::Unary(BinaryRhsScalarFunctor<binary_op, Src, Dst>(GetValue<Src>(src1)),
                                  elem_cnt, reinterpret_cast<Dst*>(dst),
                                  reinterpret_cast<const Src*>(src0), cuda_stream->cuda_stream())));
  }
  void Launch(Stream* stream, size_t num_src0_dims, const int64_t* src0_dims, const void* src0,
              size_t num_src1_dims, const int64_t* src1_dims, const void* src1,
              void* dst) override {
    DispatchLaunch<binary_op, Src, Dst>(
        stream, num_src0_dims, src0_dims, reinterpret_cast<const Src*>(src0), num_src1_dims,
        src1_dims, reinterpret_cast<const Src*>(src1), reinterpret_cast<Dst*>(dst));
  }
};

template<BinaryOp binary_op, typename Src, typename Dst>
std::unique_ptr<BroadcastElementwiseBinary> NewBroadcastElementwiseBinary() {
  return std::unique_ptr<BroadcastElementwiseBinary>(
      new BroadcastElementwiseBinaryImpl<binary_op, Src, Dst>());
}

}  // namespace primitive
}  // namespace ep

}  // namespace oneflow
