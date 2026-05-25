### Nomos testnet

Node version: `0.2.1`

Deployment following the description in [logos-blockchain releases GitHub](https://github.com/logos-blockchain/logos-blockchain/releases/tag/0.2.1).

Nodes will use host IP directly and `NodePort` services starting from 31000. Services for 100 nodes are pregenerated 
already. Update if necessary

Set to push metrics to vaclab OTLP, and logging level is changed to `INFO` (see `logos-blockchain.yaml` args).

Nodes are deployed sequentially after each one finish `Bootstrapping` and goes to `Online` state.   