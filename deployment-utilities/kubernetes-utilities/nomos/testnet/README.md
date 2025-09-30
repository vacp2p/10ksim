### Nomos testnet

Nomos commit: `93670895e716f9dbe1e5c96e3f157fee979749a9`

Basic example of a Nomos testnet in Kubernetes. **Currently not working**.

`cfgsync.yaml` is used to sync the Nomos nodes. In the nomos repository, there is another `cfgsync.yaml` for the configuration.
This has a variable `n_hosts: 4` that needs to match with the number of Nomos nodes that will be deployed.

Instead of deploying Loki for logs gathering, for quick test it is recommented to change that configuration like:
```
# Tracing
tracing_settings:
  # logger: !Loki
  #   endpoint: http://loki:3100/
  #   host_identifier: node
  logger: !Stdout
```

