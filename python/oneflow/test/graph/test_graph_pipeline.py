import os
import sys

# For debug
os.environ["MASTER_ADDR"] = "127.0.0.1"
os.environ["MASTER_PORT"] = "8003"
os.environ["WORLD_SIZE"] = "4"
os.environ["RANK"] = str(sys.argv[1])
os.environ["LOCAL_RANK"] = str(sys.argv[1])

import unittest
import numpy as np

import oneflow as flow
import oneflow.unittest

class OFRecordDataLoader(flow.nn.Module):
    def __init__(
        self,
        ofrecord_root: str = "./ofrecord",
        mode: str = "train",  # "val"
        dataset_size: int = 9469,
        batch_size: int = 1,
        placement=None,
        sbp=None,
    ):
        super().__init__()
        channel_last = False
        output_layout = "NHWC" if channel_last else "NCHW"
        self.train_record_reader = flow.nn.OFRecordReader(
            ofrecord_root + "/" + mode,
            batch_size=batch_size,
            data_part_num=40,
            part_name_suffix_length=5,
            random_shuffle=False,
            shuffle_after_epoch=False,
            placement=placement,
            sbp=sbp,
            random_seed=0,
        )
        self.record_label_decoder = flow.nn.OFRecordRawDecoder(
            "class/label", shape=(), dtype=flow.int32
        )

        color_space = "RGB"
        height = 22
        width = 22

        self.record_image_decoder = flow.nn.OFRecordImageDecoder("encoded", color_space=color_space)

        self.resize = flow.nn.image.Resize(target_size=[height, width])

        self.batch_size = batch_size
        self.dataset_size = dataset_size

    def __len__(self):
        return self.dataset_size // self.batch_size

    def forward(self):
        train_record = self.train_record_reader()
        label = self.record_label_decoder(train_record)
        image_raw_buffer = self.record_image_decoder(train_record)
        image = self.resize(image_raw_buffer)[0]
        image = flow.flatten(image.to(flow.float32), start_dim=1)

        return image, label

D = "cuda"
B = [flow.sbp.broadcast]
P = flow.placement("cuda", {0: [0, 1, 2, 3]})
P0 = flow.placement("cuda", {0: [0]})
P0C = flow.placement("cpu", {0: [0]})
P1 = flow.placement("cuda", {0: [1]})
P2 = flow.placement("cuda", {0: [2]})
P3 = flow.placement("cuda", {0: [3]})
P3C = flow.placement("cpu", {0: [3]})

def _get_ppm_and_opt():
    train_data_loader = OFRecordDataLoader(
        ofrecord_root="/dataset/ImageNet/ofrecord",
        mode="train",
        dataset_size=400,
        batch_size=4,
        placement=P0,
        sbp=B,
    )

    class Stage0Module(flow.nn.Module):
        def __init__(self):
            super().__init__()
            self.train_data_loader = train_data_loader
            self.linear = flow.nn.Linear(1452, 8, False)
            self.linear.to_consistent(placement=P0, sbp=B)
            flow.nn.init.constant_(self.linear.weight, 0.023)

        def forward(self):
            image, label = self.train_data_loader()
            image = image.to(D)
            label = label.to(D)
            out0 = self.linear(image)
            return out0, label, image

    class Stage1Module(flow.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = flow.nn.Linear(8, 8, False)
            self.linear.to_consistent(placement=P1, sbp=B)
            flow.nn.init.constant_(self.linear.weight, 0.023)
        
        def forward(self, input):
            out0 = input.to_consistent(placement=P1, sbp=input.sbp)
            out1 = self.linear(out0)
            return out1

    class Stage2Module(flow.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = flow.nn.Linear(8, 8, False)
            self.linear.to_consistent(placement=P2, sbp=B)
            flow.nn.init.constant_(self.linear.weight, 0.023)
        
        def forward(self, input):
            out0 = input.to_consistent(placement=P2, sbp=input.sbp)
            out1 = self.linear(out0)
            return out1

    class Stage3Module(flow.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = flow.nn.Linear(8, 2, False)
            self.linear.to_consistent(placement=P3, sbp=B)
            flow.nn.init.constant_(self.linear.weight, 0.023)
        
        def forward(self, out0, label):
            out0 = out0.to_consistent(placement=P3, sbp=out0.sbp)
            label = label.to_consistent(placement=P3, sbp=out0.sbp)
            out1 = self.linear(out0)
            loss = out1.sum()
            return loss, out1

    class PipelineModule(flow.nn.Module):
        def __init__(self):
            super().__init__()
            self.stage_0_m = Stage0Module()
            self.stage_1_m = Stage1Module()
            self.stage_2_m = Stage2Module()
            self.stage_3_m = Stage3Module()

        def forward(self):
            out0, label, image = self.stage_0_m()
            out1 = self.stage_1_m(out0)
            out2 = self.stage_2_m(out1)
            out3, out3_orig = self.stage_3_m(out2, label)
            image = image.to_consistent(placement=P3, sbp=B)
            label = label.to_consistent(placement=P3, sbp=B)
            return out3, image, label, out3_orig

    pp_m = PipelineModule()
    of_sgd = flow.optim.SGD(pp_m.parameters(), lr=0.0001)
    return pp_m, of_sgd

def _test_graph_pipeline(test_case):
    rank = flow.env.get_rank()

    def train_with_graph(iter_num=3):
        pp_m, of_sgd = _get_ppm_and_opt()

        class PipelineGraph(flow.nn.Graph):
            def __init__(self):
                super().__init__()
                self.pp_m = pp_m
                self.pp_m.stage_0_m.config.stage_id = 0
                self.pp_m.stage_1_m.config.stage_id = 1
                self.pp_m.stage_2_m.config.stage_id = 2
                self.pp_m.stage_3_m.config.stage_id = 3
                self.config.set_gradient_accumulation_steps(4)
                self.add_optimizer(of_sgd)

            def build(self):
                pp_m.train()
                out, image, label, out_orig = self.pp_m()
                out.backward()
                #return out, image, label
                return image

        pp_g = PipelineGraph()
        pp_g.debug()

        def one_iter(iter_idx):
            #of_graph_out, image, label = pp_g()
            of_graph_out = pp_g()
            of_graph_out = of_graph_out.to_local()
            print("out numpy \n", of_graph_out)
            #if rank == 3:
            #    of_graph_out = of_graph_out.to_local()
            #    #of_graph_out_np = of_graph_out.numpy()
            #    print("out numpy \n", of_graph_out)
                #of_graph_out_orig = of_graph_out_orig.to_local()
                #of_graph_out_np_orig = of_graph_out_orig.numpy()
                #print("out_orig numpy \n", of_graph_out_np_orig)
                #label = label.to_local()
                #print(f"label numpy \n shape {label.shape} data {label.numpy()}")
                #image = image.to_local()
                #print(f"image numpy \n shape {image.shape} data {image}")
                #return of_graph_out_np, image.numpy(), label.numpy()

        #check_list = []
        #data_list = []
        for i in range(iter_num):
            out = one_iter(i)
        #    if rank == 3:
        #        check_list.append(out[0])
        #        data_list.append((out[1], out[2]))
        #return check_list, data_list

    def train_with_module(iter_num=3, data=None):
        class DataModule(flow.nn.Module):
            def __init__(self, data):
                super().__init__()
                self.data_list = [] 
                self.idx = 0
                for tuple_pair in data:
                    image = tuple_pair[0]
                    label = tuple_pair[1]
                    print("image ", image)
                    print("label ", label)
                    for i in range(4):
                        s = i * 4
                        e = s + 4
                        micro_batch_image = image[s:e]
                        micro_batch_label = label[s:e]
                        print("micro image ", micro_batch_image)
                        print("micro label ", micro_batch_label)
                        self.data_list.append((flow.Tensor(micro_batch_image).to("cuda:3"), flow.Tensor(micro_batch_label).to("cuda:3")))
            
            def forward(self):
                image, label = self.data_list[self.idx]
                self.idx += 1
                return image, label

        class TrainModule(flow.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = flow.nn.Linear(1452, 8, False)
                flow.nn.init.constant_(self.linear.weight, 0.023)
                self.linear.to("cuda:3")
                self.linear1 = flow.nn.Linear(8, 8, False)
                flow.nn.init.constant_(self.linear1.weight, 0.023)
                self.linear1.to("cuda:3")
                self.linear2 = flow.nn.Linear(8, 8, False)
                flow.nn.init.constant_(self.linear2.weight, 0.023)
                self.linear2.to("cuda:3")
                self.linear3 = flow.nn.Linear(8, 2, False)
                flow.nn.init.constant_(self.linear3.weight, 0.023)
                self.linear3.to("cuda:3")

            def forward(self, image, label):
                out0 = self.linear(image)
                out1 = self.linear1(out0)
                out2 = self.linear2(out1)
                out3 = self.linear3(out2)
                loss = out3.sum() 
                return loss, image, label
        
        if rank == 3:
            d_m = DataModule(data)
            t_m = TrainModule()
            of_sgd = flow.optim.SGD(t_m.parameters(), lr=0.0001)

            def one_iter(iter_idx):
                image, label = d_m()
                if rank == 3:
                    loss, image, label = t_m(image, label)
                    out_np = loss.numpy()
                    print("eager out numpy \n", out_np)
                    print(f"eager label numpy \n shape {label.shape} data {label.numpy()}")
                    print(f"eager image numpy \n shape {image.shape} data {image.numpy()}")
                    loss = loss * 0.25
                    loss.backward()
                    if iter_idx % 4 == 3:
                        print(f"iter index: {iter_idx}")
                        of_sgd.step()
                        of_sgd.zero_grad()
                    return out_np

            check_list = []
            for i in range(iter_num):
                check_list.append(one_iter(i))
            return check_list


    iter_num = 2
    train_with_graph(iter_num)
    #graph_check_list, data = train_with_graph(iter_num)
    #module_check_list = train_with_module(iter_num * 4, data)

    #if (rank == 3):
    #    for i in range(iter_num*4):
    #        # check equal on loss
    #        test_case.assertTrue(
    #            np.array_equal(module_check_list[i], graph_check_list[i//4][i%4])
    #        )


@unittest.skipIf(os.getenv("ONEFLOW_TEST_CPU_ONLY"), "only test cpu cases")
@flow.unittest.skip_unless_1n1d()
class TestGraphPipeline(oneflow.unittest.TestCase):
    def test_graph_pipeline(test_case):
        _test_graph_pipeline(test_case)


if __name__ == "__main__":
    sys.argv.pop()
    unittest.main()