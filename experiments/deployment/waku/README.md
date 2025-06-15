
File structure
.
│
├── README.md
├── builders.py
├── experiments
│   └── ...
├── <service> (bootstrap/publisher/etc)
│   ├── Chart.yaml
│   ├── values.yaml # helm will use ./values.yaml as the base/default values.yaml
│   ├── templates
│   │   └── ...
│   └── ...
└── templates # Templates common to multiple services (nodes, publisher, etc.)
    └── helpers
