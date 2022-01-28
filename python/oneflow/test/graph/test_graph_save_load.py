import unittest
import os
import numpy as np
import copy

import oneflow as flow
import oneflow.unittest


def _test_linear_graph_save_load(test_case, device):
    def train_with_graph(call_cnt=0, state_dict=None):
        linear = flow.nn.Linear(3, 8)
        linear = linear.to(device)
        flow.nn.init.constant_(linear.weight, 2.068758)
        flow.nn.init.constant_(linear.bias, 0.23)
        of_sgd = flow.optim.SGD(linear.parameters(), lr=0.001, momentum=0.9)

        x = flow.tensor(
            [
                [-0.94630778, -0.83378579, -0.87060891],
                [2.0289922, -0.28708987, -2.18369248],
                [0.35217619, -0.67095644, -1.58943879],
                [0.08086036, -1.81075924, 1.20752494],
                [0.8901075, -0.49976737, -1.07153746],
                [-0.44872912, -1.07275683, 0.06256855],
                [-0.22556897, 0.74798368, 0.90416439],
                [0.48339456, -2.32742195, -0.59321527],
            ],
            dtype=flow.float32,
            device=device,
            requires_grad=False,
        )

        class LinearTrainGraph(flow.nn.Graph):
            def __init__(self):
                super().__init__()
                self.linear = linear
                self.add_optimizer(of_sgd)

            def build(self, x):
                out = self.linear(x)
                out = out.sum()
                out.backward()
                return out

        print(f"===Call count num {call_cnt}===", flush=True)
        linear_t_g = LinearTrainGraph()
        #linear_t_g.debug(2)
        if (state_dict):
            print("---Load state dict---", flush=True)
            linear_t_g.load_state_dict(state_dict)
            # Check state in module has been loaded.
            test_case.assertTrue(np.array_equal(state_dict["linear"]["weight"].numpy(), linear.weight))
            test_case.assertTrue(np.array_equal(state_dict["linear"]["bias"].numpy(), linear.bias))

        print("---Iter 0---", flush=True)
        of_graph_out = linear_t_g(x)
        iter0_state_dict = linear_t_g.state_dict()
        if (state_dict):
            # Check wild variable state initialized in job has been loaded.
            cur_train_step = iter0_state_dict["System-Train-TrainStep"].to_local().numpy()[0]
            test_case.assertTrue(3 == cur_train_step)
        print("Iter 0 state dict: ", iter0_state_dict, flush=True)
        iter0_state_dict = copy.deepcopy(linear_t_g.state_dict())

        print("---Iter 1---", flush=True)
        of_graph_out = linear_t_g(x)
        iter1_state_dict = linear_t_g.state_dict()
        print("Iter 1 state dict: ", iter1_state_dict, flush=True)

        return iter1_state_dict


    state_dict_0 = train_with_graph(0, None)
    state_dict_1 = train_with_graph(1, state_dict_0)


@unittest.skipIf(os.getenv("ONEFLOW_TEST_CPU_ONLY"), "only test cpu cases")
@flow.unittest.skip_unless_1n1d()
class TestLinearGraphSaveLoad(oneflow.unittest.TestCase):
    def test_linear_graph_save_load_gpu(test_case):
        _test_linear_graph_save_load(test_case, flow.device("cuda"))

    def _test_linear_graph_save_load_cpu(test_case):
        _test_linear_graph_save_load(test_case, flow.device("cpu"))


if __name__ == "__main__":
    unittest.main()
