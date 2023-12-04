#!/bin/bash

# Check if 'yq' is installed
if ! command -v yq &>/dev/null; then
  echo "Error: 'yq' command not found. Please install it and make sure it's in your PATH."
  exit 1
fi

read -p "Enter the number of batches: " batches

read -p "Enter the new number of replicas (PODs) per batch: " pods

yq e ".spec.replicas = $pods" -i "template.yaml"

modified_pods=$(yq e ".spec.replicas" "template.yaml")

if [ "$modified_pods" -eq "$pods" ]; then
  echo "Replicas in Yaml updated to $pods"
else
  echo "Failed to update replicas in Yaml"
  exit 1
fi

# Number of containers to add
read -p "Enter how many containers per POD: " num_containers

total_peers=$((pods*num_containers))

# Create a copy to append
cp "template.yaml" "deploy-batch-0.yaml"

# Loop to generate and append instances
for ((i=0; i<num_containers; i++)); do
    cat <<EOF >> "deploy-batch-0.yaml"
        - name: container-$i
          image: wakuorg/nwaku:wakunode_dst
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
            - /usr/bin/wakunode --relay=true --rpc-admin=true --max-connections=250 --rpc-address=0.0.0.0 --rest=true --rest-admin=true --rest-private=true --rest-address=0.0.0.0 --discv5-discovery=true --discv5-enr-auto-update=True --log-level=INFO --rpc-address=0.0.0.0 --metrics-server=True --metrics-server-address=0.0.0.0 --discv5-bootstrap-node=\$ENR1 --discv5-bootstrap-node=\$ENR2 --discv5-bootstrap-node=\$ENR3 --nat=extip:\${IP} --pubsub-topic="/waku/2/kubetopic" --ports-shift=$i
EOF
done


for ((i=1; i<batches; i++)); do
    cp "deploy-batch-0.yaml" "deploy-batch-$i.yaml"
    yq e '.metadata.name = "nodes-'$i'"' -i "deploy-batch-$i.yaml"
    yq e '.spec.selector.matchLabels.app = "nodes-'$i'"' -i "deploy-batch-$i.yaml"
    yq e '.spec.template.metadata.labels.app = "nodes-'$i'"' -i "deploy-batch-$i.yaml"
    yq e '.spec.template.spec.topologySpreadConstraints[0].labelSelector.matchLabels.type = "nodes-'$i'"' -i "deploy-batch-$i.yaml"
done

sudo kubectl -n zerotesting delete networkpolicy zerotesting-policy

sudo kubectl create namespace zerotesting

sudo kubectl apply -f bootstrap.yaml

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
for ((j=0; j<batches; j++)); do
    for ((i=0; i<pods; i++)); do
        cat <<EOF >> "services.yaml"
apiVersion: v1
kind: Service
metadata:
  name: nodes-$((i + pods*j))
  namespace: zerotesting
spec:
  selector:
    statefulset.kubernetes.io/pod-name: nodes-$j-$i
  ports:
EOF
        for ((port=8645; port<$((8645 + num_containers)); port++)); do
            cat <<EOF >> "services.yaml"
    - name: port-$port
      protocol: TCP
      port: $port
      targetPort : $port
EOF
        done
        cat <<EOF >> "services.yaml"
  type: ClusterIP
---
EOF
    done
done

sudo kubectl apply -f network-policy.yaml

echo "Deploying nodes..."
for ((i=0; i<batches; i++)); do
    sudo kubectl apply -f deploy-batch-$i.yaml
    echo "Waiting 60 seconds for next batch..."
    sleep 60
done

echo "Creating services..."
sudo kubectl apply -f services.yaml

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
        - python /publisher/traffic.py --multiple-nodes=http://nodes-[0..$pods]:8645 --msg-size-kbytes=10 --delay-seconds=1 -cpp $num_containers
  volumes:
  - name: data-volume
    hostPath:
      path: /home/alber/10k/waku/publisher_script
EOF

echo "Deploying publisher"
sudo kubectl apply -f publisher.yaml

echo "Done"
