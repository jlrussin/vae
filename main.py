from __future__ import print_function
import argparse
import torch
import numpy as np
import matplotlib.pyplot as plt
import torch.utils.data
from torch import nn, optim
from torch.nn import functional as F
from torchvision import datasets, transforms
from torchvision.utils import save_image

parser = argparse.ArgumentParser(description='VAE MNIST Example')
parser.add_argument('--batch_size', type=int, default=128, metavar='N',
                    help='input batch size for training (default: 128)')
parser.add_argument('--epochs', type=int, default=10, metavar='N',
                    help='number of epochs to train (default: 10)')
parser.add_argument('--no_cuda', action='store_true', default=False,
                    help='enables CUDA training')
parser.add_argument('--seed', type=int, default=1, metavar='S',
                    help='random seed (default: 1)')
parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
parser.add_argument('--results_dir',default='results/standard/',
                    help='Directory for storing images')
parser.add_argument('--variance_type',default='standard',
                    choices=['standard', 'equal', 'fixed'])
args = parser.parse_args()
args.cuda = not args.no_cuda and torch.cuda.is_available()

torch.manual_seed(args.seed)

device = torch.device("cuda" if args.cuda else "cpu")

kwargs = {'num_workers': 1, 'pin_memory': True} if args.cuda else {}
train_loader = torch.utils.data.DataLoader(
    datasets.MNIST('../data', train=True, download=True,
                   transform=transforms.ToTensor()),
    batch_size=args.batch_size, shuffle=True, **kwargs)
test_loader = torch.utils.data.DataLoader(
    datasets.MNIST('../data', train=False, transform=transforms.ToTensor()),
    batch_size=args.batch_size, shuffle=True, **kwargs)


class VAE(nn.Module):
    def __init__(self, variance_type = 'standard'):
        super(VAE, self).__init__()

        self.fc1 = nn.Linear(784, 400)
        self.fc21 = nn.Linear(400, 20)
        if variance_type == 'standard':
            self.fc22 = nn.Linear(400, 20)
        elif variance_type == 'equal':
            self.fc22 = nn.Linear(400,1)
        elif variance_type == 'fixed':
            self.sigma = nn.Parameter(torch.ones(20))
        self.fc3 = nn.Linear(20, 400)
        self.fc4 = nn.Linear(400, 784)
        self.variance_type = variance_type

    def encode(self, x):
        h1 = F.relu(self.fc1(x))
        mu = self.fc21(h1)
        if self.variance_type == 'standard':
            sigma = self.fc22(h1) # vector size 20
        elif self.variance_type == 'equal':
            sigma = self.fc22(h1) # scalar
        elif self.variance_type == 'fixed':
            sigma = self.sigma
        return mu, sigma

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5*logvar)
            eps = torch.randn_like(mu)
            return eps.mul(std).add_(mu)
        else:
            return mu

    def decode(self, z):
        h3 = F.relu(self.fc3(z))
        return torch.sigmoid(self.fc4(h3))

    def forward(self, x):
        mu, logvar = self.encode(x.view(-1, 784))
        z = self.reparameterize(mu, logvar)
        return self.decode(z), mu, logvar


model = VAE(variance_type = args.variance_type).to(device)
optimizer = optim.Adam(model.parameters(), lr=1e-3)


# Reconstruction + KL divergence losses summed over all elements and batch
def loss_function(recon_x, x, mu, logvar):
    BCE = F.binary_cross_entropy(recon_x, x.view(-1, 784), reduction='sum')

    # see Appendix B from VAE paper:
    # Kingma and Welling. Auto-Encoding Variational Bayes. ICLR, 2014
    # https://arxiv.org/abs/1312.6114
    # 0.5 * sum(1 + log(sigma^2) - mu^2 - sigma^2)
    KLD = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())

    return BCE + KLD


def train(epoch):
    model.train()
    train_loss = 0
    train_loss_data = []
    for batch_idx, (data, _) in enumerate(train_loader):
        data = data.to(device)
        optimizer.zero_grad()
        recon_batch, mu, logvar = model(data)
        loss = loss_function(recon_batch, data, mu, logvar)
        loss.backward()
        train_loss += loss.item()
        train_loss_data.append(loss.item() / len(data))
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader),
                loss.item() / len(data)))

    print('====> Epoch: {} Average loss: {:.4f}'.format(
          epoch, train_loss / len(train_loader.dataset)))
    return train_loss_data



def test(epoch):
    model.eval()
    test_loss = 0
    with torch.no_grad():
        for i, (data, _) in enumerate(test_loader):
            data = data.to(device)
            recon_batch, mu, logvar = model(data)
            test_loss += loss_function(recon_batch, data, mu, logvar).item()
            if i == 0:
                n = min(data.size(0), 8)
                comparison = torch.cat([data[:n],
                                      recon_batch.view(args.batch_size, 1, 28, 28)[:n]])
                save_image(comparison.cpu(),
                         args.results_dir + args.variance_type + '_'
                         'reconstruction_' + str(epoch) + '.png', nrow=n)

    test_loss /= len(test_loader.dataset)
    print('====> Test set loss: {:.4f}'.format(test_loss))
    return test_loss


if __name__ == "__main__":
    train_loss_data = []
    test_loss_data = []
    for epoch in range(1, args.epochs + 1):
        train_loss_data_i = train(epoch)
        test_loss_i = test(epoch)
        train_loss_data.append(train_loss_data_i)
        test_loss_data.append(test_loss_i)
        with torch.no_grad():
            sample = torch.randn(64, 20).to(device)
            sample = model.decode(sample).cpu()
            save_image(sample.view(64, 1, 28, 28),
                       args.results_dir + args.variance_type + '_'
                       'sample_' + str(epoch) + '.png')
    test_batch_ids = np.cumsum([len(l) for l in train_loss_data])
    flat_train_data = [v for l in train_loss_data for v in l]
    batch_ids = range(len(flat_train_data))
    plt.plot(batch_ids,flat_train_data)
    plt.plot(test_batch_ids,test_loss_data)
    plt.ylim([0,200])
    plt.ylabel("Loss")
    plt.xlabel("Batch number")
    plt.title("Training and testing curves for %s" % args.variance_type)
    plt.legend(["Train","Test"])
    plt.savefig(args.results_dir + args.variance_type + '_' + 'training_curves.png')
