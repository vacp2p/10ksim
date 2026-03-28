#!/bin/bash
NAMESPACE="nimlibp2p"

kubectl apply -f bootstrap.yaml
kubectl rollout status --watch --timeout=600s statefulset/bootstrap -n $NAMESPACE

kubectl apply -f nodes.yaml
kubectl rollout status --watch --timeout=600s statefulset/nodes -n $NAMESPACE

kubectl apply -f probe.yaml
kubectl rollout status --watch --timeout=600s statefulset/nodes -n $NAMESPACE

sleep 60
./cleanup.sh