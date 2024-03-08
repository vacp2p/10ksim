sed -i "/^node-ip: /c\node-ip: $(ip -4 addr show enp2s0 | awk '/inet/{print $2}' | cut -d/ -f1)" /etc/rancher/rke2/config.yaml
