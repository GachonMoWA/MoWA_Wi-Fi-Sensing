import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.nn.functional as F
import numpy as np
from util import euclidean_dist
from ReWiS_model import *

class ProtoNet(nn.Module):
    def __init__(self, encoder):
        """
        Args:
            encoder : CNN encoding the dataloader dataframes in sample
            n_way (int): number of classes in a classification task
            n_support (int): number of labeled examples per class in the support set
            n_query (int): number of labeled examples per class in the query set
        """
        super(ProtoNet, self).__init__()
        self.encoder = encoder.cuda(0)

    def proto_train(self, sample):
        """
                Computes loss, accuracy and output for classification task
                Args:
                    sample (torch.Tensor): shape (n_way, n_support+n_query, (dim))
                Returns:
                    torch.Tensor: shape(2), loss, accuracy and y_hat
                """
        sample_images = sample['csi_mats'].cuda(0)
        n_way = sample['n_way']
        n_support = sample['n_support']
        n_query = sample['n_query']

        x_support = sample_images[:, :n_support]
        x_query = sample_images[:, n_support:]

        # target indices are 0 ... n_way-1
        target_inds = torch.arange(0, n_way).view(n_way, 1, 1).expand(n_way, n_query, 1).long()
        target_inds = Variable(target_inds, requires_grad=False)
        target_inds = target_inds.cuda(0)

        # encode dataloader dataframes of the support and the query set
        '''
        Modified
        # Separate support and query tensor
        '''
        x_support = x_support.contiguous().view(n_way * n_support, *x_support.size()[2:])
        x_query = x_query.contiguous().view(n_way * n_query, *x_query.size()[2:])

        z_support = self.encoder.forward(x_support)
        z_query = self.encoder.forward(x_query)
        z_support_dim = z_support.size(-1)
        z_proto = z_support.view(n_way, n_support, z_support_dim).mean(1)

        # compute distances
        dists = euclidean_dist(z_query, z_proto)

        # compute probabilities
        log_p_y = F.log_softmax(-dists, dim=1).view(n_way, n_query, -1)

        loss_val = -log_p_y.gather(2, target_inds).squeeze().view(-1).mean()
        _, y_hat = log_p_y.max(2)
        acc_val = torch.eq(y_hat, target_inds.squeeze()).float().mean()  # y_hat과 gt 같은지 비교

        return loss_val, {
            'loss': loss_val.item(),
            'acc': acc_val.item(),
            'y_hat': y_hat
            # ,'target':target
        }

    def create_protoNet(self, support_sample):
        """
        Computes loss, accuracy and output for classification task
        Args:
            sample (torch.Tensor): shape (n_way, n_support+n_query, (dim))
        Returns:
            torch.Tensor: shape(2), loss, accuracy and y_hat
        """
        sample_images = support_sample['s_csi_mats'].cuda(0)
        n_way = support_sample['n_way']
        n_support = support_sample['n_support']

        x_support = sample_images

        # encode dataloader dataframes of the support and the query set
        '''
        Modified
        # Separate support and query tensor
        '''
        x_support = x_support.contiguous().view(n_way * n_support, *x_support.size()[2:])

        z_support = self.encoder.forward(x_support)
        z_support_dim = z_support.size(-1)
        z_proto = z_support.view(n_way, n_support, z_support_dim).mean(1)

        return z_proto

    def proto_test(self, query_sample, z_proto, n_way, gt):
        sample_images = query_sample.cuda(0)
        n_query = 1

        gt_mat = torch.tensor([gt] * n_way).cuda(0)

        x_query = sample_images
        x_query = x_query.contiguous().view(*x_query.size())
        z_query = self.encoder.forward(x_query)

        # compute distances
        dists = euclidean_dist(z_query, z_proto)

        # compute probabilities
        log_p_y = F.log_softmax(-dists, dim=1).view(n_way, n_query, -1)
        _, y_hat = log_p_y.max(2)
        acc_val = torch.eq(y_hat, gt_mat).float().mean()  # y_hat과 gt 같은지 비교

        print('label:{}, acc:{}'.format(gt, acc_val))

        return {
            'acc': acc_val.item(),
            'y_hat': y_hat
            # ,'target':target
        }

class Flatten(nn.Module):
    def __init__(self):
        super(Flatten, self).__init__()

    def forward(self, x):
        return x.view(x.size(0), -1)

def load_protonet_conv(**kwargs):
    """
    Loads the prototypical network models
    Arg:
        x_dim (tuple): dimension of input dataloader dataframes
        hid_dim (int): dimension of hidden layers in conv blocks
        z_dim (int): dimension of embedded dataloader dataframes
    Returns:
        Model (Class ProtoNet)
    """
    x_dim = kwargs['x_dim']
    hid_dim = kwargs['hid_dim']
    z_dim = kwargs['z_dim']

    def conv_block(in_channels, out_channels):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=(1, 3), padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )

    encoder = nn.Sequential(
        conv_block(x_dim[0], hid_dim),
        conv_block(hid_dim, hid_dim),
        conv_block(hid_dim, hid_dim),
        # conv_block(hid_dim, hid_dim),
        # conv_block(hid_dim, hid_dim),
        # conv_block(hid_dim, hid_dim),
        # conv_block(hid_dim, hid_dim),
        conv_block(hid_dim, z_dim),
        Flatten()
    )

    return ProtoNet(encoder)

def load_protonet_vit():

    encoder = ReWiS_ViT(
        in_channels=1,  # 입력 채널 수
        patch_size=[22, 22],  # 패치 크기 (가로, 세로)
        embed_dim=64,  # 임베딩 차원
        num_layers=12,  # Transformer 블록 수
        num_heads=8,  # 멀티헤드 어텐션에서의 헤드 수
        mlp_dim=4,  # MLP의 확장 비율
        num_classes=4,  # 분류할 클래스 수
        in_size=[242, 242]  # 입력 이미지 크기 (가로, 세로)
    )

    return ProtoNet(encoder)