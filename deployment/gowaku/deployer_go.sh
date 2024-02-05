#!/bin/bash

# Check if 'yq' is installed
if ! command -v yq &>/dev/null; then
  echo "Error: 'yq' command not found. Please install it and make sure it's in your PATH."
  exit 1
fi

read -p "Enter the new number of replicas (PODs): " pods

yq e ".spec.replicas = $pods" -i "template.yaml"

modified_pods=$(yq e ".spec.replicas" "template.yaml")

if [ "$modified_pods" -eq "$pods" ]; then
  echo "Replicas in Yaml updated to $pods"
else
  echo "Failed to update replicas in Yaml"
  exit 1
fi

# Create a copy to append
cp "template.yaml" "deploy.yaml"

# Loop to generate and append instances
for ((i=0; i<num_containers; i++)); do
    cat <<EOF >> "deploy.yaml"
        - name: container-$i
          image: gowaku:local
          env:
            - name: IP
              valueFrom:
                fieldRef:
                  fieldPath: status.podIP
            - name: ENR1
              valueFrom:
                configMapKeyRef:
                  name: pod-enr-config
                  key: ENR1
            - name: ENR2
              valueFrom:
                configMapKeyRef:
                  name: pod-enr-config
                  key: ENR2
            - name: ENR3
              valueFrom:
                configMapKeyRef:
                  name: pod-enr-config
                  key: ENR3
          command:
            - sh
            - -c
            - /usr/bin/waku --relay=true --rpc-admin=true --max-connections=250 --rpc-address=0.0.0.0 --rest=true --rest-admin=true --rest-address=0.0.0.0 --discv5-discovery=true --discv5-enr-auto-update=True --log-level=INFO --rpc-address=0.0.0.0 --metrics-server=True --metrics-server-address=0.0.0.0 --discv5-bootstrap-node=\$ENR1 --discv5-bootstrap-node=\$ENR2 --discv5-bootstrap-node=\$ENR3 --pubsub-topic="/waku/2/kubetopic" --nat=extip:\${IP}
EOF
done

sudo kubectl -n zerotesting delete networkpolicy zerotesting-policy

sudo kubectl create namespace zerotesting

sudo kubectl apply -f bootstrap_go.yaml

echo "Sleeping 10 seconds to let bootstrap to set up..."
sleep 10

echo "Getting bootstrap ips..."
pod_ips=()
ip_1=$(sudo kubectl get pod bootstrap-1 -n zerotesting -o jsonpath='{.status.podIP}')
pod_ips+=("$ip_1")
echo $ip_1
ip_2=$(sudo kubectl get pod bootstrap-2 -n zerotesting -o jsonpath='{.status.podIP}')
pod_ips+=("$ip_2")
echo $ip_2
ip_3=$(sudo kubectl get pod bootstrap-3 -n zerotesting -o jsonpath='{.status.podIP}')
pod_ips+=("$ip_3")
echo $ip_3

if [ -z "$pod_ips" ]; then
    echo "Error: Unable to retrieve pod IP."
    exit 1
fi

config_map_yaml="apiVersion: v1
kind: ConfigMap
metadata:
  name: pod-enr-config
  namespace: zerotesting
data:"


index=1
for pod_ip in "${pod_ips[@]}"; do
  enr=$(wget -O - --post-data='{"jsonrpc":"2.0","method":"get_waku_v2_debug_v1_info","params":[],"id":1}' --header='Content-Type:application/json' $pod_ip:8545 2> /dev/null | sed 's/.*"enrUri":"\([^"]*\)".*/\1/')
  echo $enr
  if [ -z "$enr" ]; then
    echo "Error: Unable to retrieve bootstrap ENR."
    exit 1
  fi
  config_map_yaml+="\n  ENR$index: \"$enr\""
  ((index++))
done

echo -e "$config_map_yaml" > config-map.yaml

sudo kubectl delete -f  config-map.yaml  -n zerotesting

sudo kubectl apply -f config-map.yaml


echo "Adding services to yaml"
# Loop to generate and append instances
for ((i=0; i<pods; i++)); do
    cat <<EOF >> "deploy.yaml"
---
apiVersion: v1
kind: Service
metadata:
  name: nodes-$i
  namespace: zerotesting
spec:
  selector:
    statefulset.kubernetes.io/pod-name: nodes-$i
  ports:
EOF
    for ((port=8645; port<$((8645 + num_containers)); port++)); do
        cat <<EOF >> "deploy.yaml"
    - name: port-$port
      protocol: TCP
      port: $port
      targetPort : $port
EOF
    done
    cat <<EOF >> "deploy.yaml"
  type: ClusterIP
EOF
done

sudo kubectl apply -f network-policy.yaml

echo "Deploying nodes..."
sudo kubectl apply -f deploy.yaml

echo "Waiting 30 seconds to deploy publisher..."
sleep 30

rm publisher.yaml
cat <<EOF >> "publisher.yaml"
apiVersion: v1
kind: Pod
metadata:
  name: publisher
  namespace: zerotesting
spec:
  containers:
    - name: publisher-container
      image: publisher:local
      volumeMounts:
      - name: data-volume
        mountPath: /publisher
      command:
        - sh
        - -c
        - python /publisher/traffic.py -n=$pods --msg-size-kbytes=40 --delay-seconds=1
  volumes:
  - name: data-volume
    hostPath:
      path: /home/alber/10k/waku/publisher_script
EOF

echo "Deploying publisher"
sudo kubectl apply -f publisher.yaml

echo "Done"
