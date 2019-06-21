#include "oneflow/core/operator/esac_op.h"
#include "oneflow/core/job/sbp_signature_builder.h"
#include "oneflow/core/graph/logical_node.h"

namespace oneflow {

void EsacOp::InitFromOpConf() {
  EnrollRepeatedInputBn("in", false);
  EnrollOutputBn("out", false);
}

void EsacOp::InferBlobDescs(std::function<BlobDesc*(const std::string&)> GetBlobDesc4BnInOp,
                            const ParallelContext* parallel_ctx) const {
  BlobDesc* out = GetBlobDesc4BnInOp("out");
  out->mut_shape() = Shape({1});
  const DataType data_type = op_conf().esac_conf().data_type();
  CHECK(IsIntegralDataType(data_type));
  out->set_data_type(data_type);
}

const PbMessage& EsacOp::GetCustomizedConf() const { return op_conf().esac_conf(); }

void EsacOp::InferHasBatchDim(std::function<bool*(const std::string&)> HasBatchDim4BnInOp) const {
  *HasBatchDim4BnInOp("out") = false;
}

void EsacOp::GetSbpSignatures(
    const std::function<const BlobDesc&(const std::string&)>& LogicalBlobDesc4Ibn,
    SbpSignatureList* sbp_sig_list) const {}

LogicalNode* EsacOp::NewProperLogicalNode() const { return new EsacLogicalNode(); }

REGISTER_CPU_OP(OperatorConf::kEsacConf, EsacOp);

}  // namespace oneflow
