from __future__ import absolute_import

import oneflow.python.framework.placement_context as placement_context
import oneflow.python.framework.job_builder as job_builder
from contextlib import contextmanager

@contextmanager
def CurJob(job):
    _ResetCurJob(job)
    yield None
    _ResetCurJob(None)

class BeforeNonInputOpBuildAndInferHook:
    def __init__(self, hook):
        self.hook_ = hook

    def __enter__(self):
        before_non_input_op_build_and_infer_hooks.append(self.hook_)

    def __exit__(self, *arg):
        global before_non_input_op_build_and_infer_hooks
        before_non_input_op_build_and_infer_hooks = []

def CurJobAddOp(op_conf): return _CurJobAddNonInputOp(op_conf)

def CurJobAddInputOp(op_conf):
    op_conf.device_type = placement_context.CurPlacementGroupGetDeviceType(op_conf)
    job_builder.CurCtxAddAndInferOp(op_conf, placement_context.ParallelConf4OpConf(op_conf))
    placement_context.CurPlacementGroupAddOpConf(op_conf)

def _CurJobAddNonInputOp(op_conf):
    _prefixing_op_name_if_need(op_conf)
    op_conf.device_type = placement_context.CurPlacementGroupGetDeviceType(op_conf)
    for callback in before_non_input_op_build_and_infer_hooks: callback()
    job_builder.CurCtxAddAndInferOp(op_conf, placement_context.ParallelConf4OpConf(op_conf))
    placement_context.CurPlacementGroupAddOpConf(op_conf)

def _ResetCurJob(job):
    global cur_job
    cur_job = job
    global cur_job_var_op_name2var_blob
    cur_job_var_op_name2var_blob = {}
    global cur_job_variable_scope_stack
    assert len(cur_job_variable_scope_stack) == 0
    cur_job_variable_scope_stack = []


def _prefixing_op_name_if_need(op_conf):
    if op_conf.HasField("variable_conf"):
        return

    if op_conf.HasField("decode_ofrecord_conf"):
        return

    if op_conf.HasField("layer_norm_conf"):
        pass

    op_conf.name = _get_variable_prefix() + op_conf.name


def _get_variable_prefix():
    global cur_job_variable_scope_stack
    if len(cur_job_variable_scope_stack) == 0:
        return ""

    return "-".join(cur_job_variable_scope_stack) + "-"


cur_job = None
cur_job_var_op_name2var_blob = {}
before_non_input_op_build_and_infer_hooks = []
cur_job_variable_scope_stack = []
