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
from .optimizer import Optimizer
from .lr_scheduler import LRScheduler


class LinearLR(LRScheduler):
    """Decays the learning rate of each parameter group by linearly changing small
    multiplicative factor until the number of step reaches a pre-defined milestone: total_iters.

    Args:
        optimizer (Optimizer): Wrapped optimizer.
        start_factor (float): The number we multiply learning rate in the first step.
            The multiplication factor changes towards end_factor in the following steps.
            Default: 1./3.
        end_factor (float): The number we multiply learning rate at the end of linear changing
            process. Default: 1.0.
        total_iters (int): The number of iterations that multiplicative factor reaches to 1.
            Default: 5.
        last_step (int): The index of the last step. Default: -1.
        verbose (bool): If ``True``, prints a message to stdout for
            each update. Default: ``False``.

    Example:
        >>> # Assuming optimizer uses lr = 0.05 for all groups
        >>> # lr = 0.025    if step == 0
        >>> # lr = 0.03125  if step == 1
        >>> # lr = 0.0375   if step == 2
        >>> # lr = 0.04375  if step == 3
        >>> # lr = 0.05    if step >= 4
        >>> scheduler = LinearLR(self.opt, start_factor=0.5, total_iters=4)
        >>> for step in range(100):
        >>>     train(...)
        >>>     validate(...)
        >>>     scheduler.step()
    """

    def __init__(
        self,
        optimizer: Optimizer,
        start_factor: float = 1.0 / 3,
        end_factor: float = 1.0,
        total_iters: int = 5,
        last_step: int = -1,
        verbose: bool = False,
    ):
        assert isinstance(optimizer, Optimizer)

        if start_factor > 1.0 or start_factor < 0:
            raise ValueError(
                "Starting multiplicative factor expected to be between 0 and 1."
            )

        if end_factor > 1.0 or end_factor < 0:
            raise ValueError(
                "Ending multiplicative factor expected to be between 0 and 1."
            )

        self._start_factor = start_factor
        self._end_factor = end_factor
        self._total_iters = total_iters
        super().__init__(optimizer, last_step, verbose)

    def get_lr(self):
        if self.last_step < self._total_iters:
            multiplier = self._start_factor + (
                self._end_factor - self._start_factor
            ) * (self.last_step / self._total_iters)
            lrs = [base_lr * multiplier for base_lr in self.base_lrs]
        else:
            lrs = [base_lr for base_lr in self.base_lrs]

        return lrs

    def _generate_conf_for_graph(self, opt_confs):
        raise NotImplementedError("LinearLR is not supported in graph mode")
