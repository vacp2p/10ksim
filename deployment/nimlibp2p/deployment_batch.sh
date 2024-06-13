#!/bin/bash

YAMLS=("lazy/deploy_100b-mplex-1.2.yaml" "lazy/deploy_100b-mplex-1.3.yaml" "lazy/deploy_100b-yamux-1.2.yaml" "lazy/deploy_100b-yamux-1.3.yaml" "lazy/deploy_1000b-mplex-1.2.yaml" "lazy/deploy_1000b-mplex-1.3.yaml" "lazy/deploy_1000b-yamux-1.2.yaml" "lazy/deploy_1000b-yamux-1.3.yaml")

# Nested loops to iterate over nodes and publisher files
for nodes_file in "${YAMLS[@]}"; do
  kubectl apply -f $nodes_file
  sleep 60
  ./cleanup.sh
  sleep 60
done


