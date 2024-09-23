# Timestamp
echo "Started at $(date)"
# Spawn bootstrap nodes
kubectl apply -f bootstrap.yaml
# Wait to see that they're healthy
kubectl rollout status --watch --timeout=30000s statefulset/bootstrap -n zerotesting
# Spawn all the nodes
kubectl apply -f nodes-nwaku.yaml
kubectl apply -f nodes-gowaku-preview.yaml
echo "We have deployed all nodes, please watch Prometheus or Grafana to see when they have reached a healthy state."
kubectl rollout status --watch --timeout=30000s statefulset/nodes -n zerotesting
echo "We believe everything has rolled out. Deploying publisher now."
kubectl apply -f publisher.yaml
# Timestamp
echo "Deploying publisher at $(date)"
echo "We have deployed the publisher, please watch Grafana to see if it's working."
# 2100 seconds or 35 minutes
for i in {0..209}
do
  timeelapsed=$(10*(i+1))
  echo "Sleeping for 10 seconds, $timeelapsed/2100 seconds"
  sleep 10
done
# Tear down publisher
# Timestamp
echo "We'll stop publishing. Stopped publisher at $(date)"

kubectl delete -f publisher.yaml
# Wait 60 seconds for publisher to despawn
echo "Now we'll tear down the whole cluster. Stopped cluster at $(date)"
# Tear down nodes
kubectl delete -f nodes-nwaku.yaml
kubectl delete -f nodes-gowaku.yaml
# Tear down bootstrap
kubectl delete -f bootstrap.yaml
