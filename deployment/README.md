### Automated Deployment

While the Python tool is not ready, we are using a sort of bash automated deployment script.

Before running, make sure to `prepare_env.sh` all machines that will be used in the Kubernetes cluster.

In the `gossipsub` folder, you can find the `deploy.sh` script, which can be used either for the [Nim](https://github.com/vacp2p/dst-gossipsub-test-node/tree/dockerized), [Go](https://github.com/vacp2p/dst-gossipsub-test-node-go) and [Rust](https://github.com/vacp2p/dst-gossipsub-test-node-rust) libp2p implementations that were use for the [following results](https://www.notion.so/Nim-Rust-Go-comparison-9dc4e4c3c0914773971608e8af911943).

The `deploy.sh` script will call `kubectl`, so it is assumed that you have a Kubernetes cluster [configured](https://www.notion.so/K3s-Configuration-b495ecefade6477c9cbff82e5fff2e5d).
The results were extracted using `kube-prometheus-stack` helm chart, and the `get_logs.sh` script is used to obtain the logs of all PODs that will be used to get the time plots.

Both `nwaku` and `gowaku` folder have the same, but with small variances to work with nWaku.
Multi-container per pod is now a bit outdated, so please use 1 container per POD when asked in `deploy.sh`.
