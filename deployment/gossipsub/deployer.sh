#!/bin/bash

# Check if 'yq' is installed
if ! command -v yq &>/dev/null; then
  echo "Error: 'yq' command not found. Please install it and make sure it's in your PATH."
  exit 1
fi

read -p "Yaml template file: " YAML_FILE

if [ ! -f "$YAML_FILE" ]; then
  echo "YAML file not found: $YAML_FILE"
  exit 1
fi

read -p "Minute to run the node: " minute
read -p "Hour to run the node: " hour


read -p "Enter the new number of replicas (PODs): " NEW_REPLICAS

yq e ".spec.replicas = $NEW_REPLICAS" -i "$YAML_FILE"

MODIFIED_REPLICAS=$(yq e ".spec.replicas" "$YAML_FILE")

if [ "$MODIFIED_REPLICAS" -eq "$NEW_REPLICAS" ]; then
  echo "Replicas in Yaml updated to $NEW_REPLICAS"
else
  echo "Failed to update replicas in Yaml"
  exit 1
fi

# Number of containers to add
read -p "Enter how many containers per POD: " num_containers

read -p "Enter message size (in Bytes): " msg_size

total_peers=$((NEW_REPLICAS*num_containers))

# Create a copy to append
cp "$YAML_FILE" "deploy.yaml"

# Loop to generate and append instances
for ((i=0; i<num_containers; i++)); do
    cat <<EOF >> "deploy.yaml"
      - name: container-$i
        image: dst-test-node:local
        ports:
        - containerPort: 5000
        args: ["$minute", "$hour"]
        env:
        - name: PEERNUMBER
          value: "$i"
        - name: PEERS
          valueFrom:
            configMapKeyRef:
              name: my-app-configmap
              key: PEERS
        - name: CONNECTTO
          valueFrom:
            configMapKeyRef:
              name: my-app-configmap
              key: CONNECTTO
        - name: PEERSPERPOD
          valueFrom:
            configMapKeyRef:
              name: my-app-configmap
              key: PEERSPERPOD
        - name: MSGRATE
          valueFrom:
            configMapKeyRef:
              name: my-app-configmap
              key: MSGRATE
        - name: MSGSIZE
          valueFrom:
            configMapKeyRef:
              name: my-app-configmap
              key: MSGSIZE
EOF
done


# Loop to generate and append instances
for ((i=0; i<$NEW_REPLICAS; i++)); do
    cat <<EOF >> "deploy.yaml"
---
apiVersion: v1
kind: Service
metadata:
  name: pod-$i
  namespace: 10k-namespace
spec:
  selector:
    statefulset.kubernetes.io/pod-name: pod-$i
  ports:
EOF
for ((port=5000; port<$((5000 + num_containers)); port++)); do
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

rm config-map.yaml
cat <<EOF >> "config-map.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-app-configmap
  namespace: 10k-namespace
data:
  PEERS: "$total_peers"
  CONNECTTO: "10"
  PEERSPERPOD: "$num_containers"
  MSGRATE: "1000"
  MSGSIZE: "$msg_size"
EOF

rm network-policy.yaml
cat <<EOF >> "network-policy.yaml"
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: internal-policy
  namespace: 10k-namespace
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
    - from:
      - namespaceSelector:
          matchLabels:
            name: monitoring
  egress:
  - {}
EOF

sudo kubectl create namespace 10k-namespace

sudo kubectl apply -f config-map.yaml -n 10k-namespace

sudo kubectl apply -f network-policy.yaml

sudo kubectl apply -f deploy.yaml

echo "Done"
