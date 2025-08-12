#!/bin/bash

YAMLS=("lazy/v1-8-0/deploy_100b-mplex-1.8.0.yaml" "lazy/v1-8-0/deploy_100b-yamux-1.8.0.yaml"
"lazy/v1-8-0/deploy_1KB-mplex-1.8.0.yaml" "lazy/v1-8-0/deploy_1KB-yamux-1.8.0.yaml"
"lazy/v1-8-0/deploy_50KB-mplex-1.8.0.yaml" "lazy/v1-8-0/deploy_50KB-yamux-1.8.0.yaml")

KUBECONFIG="<kubeconfig>"

for nodes_file in "${YAMLS[@]}"; do
  kubectl --kubeconfig $KUBECONFIG apply -f $nodes_file
  sleep 3000
  ./cleanup.sh
  sleep 600
done


