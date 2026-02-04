# Update
sudo apt update
sudo apt upgrade -y

# Disable swap
sudo swapoff -a

# Load containerd modules
sudo modprobe overlay
sudo modprobe br_netfilter

# Load containerd modules permanently
sudo tee /etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF

# Configure IPv2 networking
sudo tee /etc/sysctl.d/k8s.conf >/dev/null <<'EOF'
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

# Install containerd
sudo apt update
sudo apt install -y containerd

# Generate config
sudo mkdir /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml

# TODO: This should not need to be manual... figure out using 'sed' or smthn
# MANUAL STEP - Edit /etc/containerd/config.toml to set SystemdCgroup = true
# [plugins.”io.containerd.grpc.v1.cri”.containerd.runtime.runc.options]
# 	...
# 	SystemdCgroup = true
# 	...

# Restart and enable containerd
sudo systemctl restart containerd
sudo systemctl enable containerd

# Install Kubernetes components
sudo apt update
sudo apt install -y curl ca-certificates apt-transport-https gnupg gpg

# Download the public signing key for the Kubernetes package repositories.
# If the folder `/etc/apt/keyrings` does not exist, it should be created before the curl command, read the note below.
# sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.34/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
sudo chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg # allow unprivileged APT programs to read this keyring

# This overwrites any existing configuration in /etc/apt/sources.list.d/kubernetes.list
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.34/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo chmod 644 /etc/apt/sources.list.d/kubernetes.list   # helps tools such as command-not-found to work correctly

# Update the sources list for the system to recognize the newly added repository
sudo apt update

# Install kubelet,kubeadm, kubectl
sudo apt install -y kubelet kubeadm kubectl

# Prevent automatic updates
sudo apt-mark hold kubelet kubeadm kubectl

# Install Helm keyring
curl -fsSL https://packages.buildkite.com/helm-linux/helm-debian/gpgkey | sudo gpg --dearmor -o /etc/apt/keyrings/helm-apt-keyring.gpg
sudo chmod 644 /etc/apt/keyrings/helm-apt-keyring.gpg

# Add helm repository
echo "deb [signed-by=/etc/apt/keyrings/helm-apt-keyring.gpg] https://packages.buildkite.com/helm-linux/helm-debian/any/ any main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo chmod 644 /etc/apt/sources.list.d/helm-stable-debian.list

# Install Helm
sudo apt-get update
sudo apt-get install helm

# Initialize the Kubernetes cluster
sudo kubeadm init --pod-network-cidr=192.168.0.0/16

# Copy kubeconfig
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# Install Calico
helm repo add projectcalico https://docs.tigera.io/calico/charts
helm repo update
helm install calico projectcalico/tigera-operator --namespace tigera-operator --create-namespace

# Allow workloads on the control-plane node
kubectl taint nodes --all node-role.kubernetes.io/control-plane-

# --------------------------------

# Clone the git repository
git clone https://github.com/AlexHag/k8.git && cd k8

# Add ArgoCD helm repository
helm repo add argo-cd https://argoproj.github.io/argo-helm

# Update deps
helm dep update charts/argo-cd/

# Install ArgoCD
helm install argo-cd charts/argo-cd/ -n argocd --create-namespace

# MANUAL STEP - Configure sealed serets before applying root-app
# Get the certificate
# kubectl get secret -n kube-system sealed-secrets-key-XXXX -o yaml > sealed-secrets-key.yaml
# Copy the certificate to the machine and create the secret
# kubectl create secret tls sealed-secrets-key \
#   --cert=tls.crt \
#   --key=tls.key \
#   --namespace=kube-system
# kubectl label secret sealed-secrets-key \
#   -n kube-system \
#   sealedsecrets.bitnami.com/sealed-secrets-key=active

# Install root-app (which will deploy sealed-secrets and all other apps)
helm template charts/root-app/ | kubectl apply -f -
