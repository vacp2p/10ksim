#!/usr/bin/env python3
"""Quick database inspection script."""

import json
from dst_dashboard.storage.db import DSTDatabase

db = DSTDatabase()

print("\n" + "="*80)
print("DATABASE CONTENTS")
print("="*80)

# Datasources
print("\n📊 DATASOURCES:")
for ds in db.datasources.find({}):
    print(f"  {ds['name']} ({ds['type']})")

# Experiments
print("\n🔬 EXPERIMENTS:")
for exp in db.experiments.find({}):
    print(f"\n  ID: {exp['id']}")
    print(f"  Title: {exp['title']}")
    print(f"  # Datasets: {len(exp.get('datasets', []))}")
    print(f"  # Panels: {len(exp.get('panels', []))}")

# Datasets
print("\n📁 DATASETS:")
for ds in db.datasets.find({}):
    print(f"\n  {ds.get('experiment_id')}:{ds.get('dataset_name')}")
    data = ds.get('data', [])
    print(f"  Rows: {len(data)}")
    if data:
        sample = data[0]
        print(f"  Fields: {list(sample.keys())}")
        print(f"  Sample: {json.dumps(sample, indent=4, default=str)}")

# Panels
print("\n📈 PANELS:")
for panel in db.panels.find({}):
    panel_data = panel.get('data', {})
    print(f"\n  {panel.get('experiment_id')}:{panel.get('name')}")
    print(f"  Type: {panel_data.get('type')}")
    print(f"  Dataset: {panel_data.get('dataset')}")
    print(f"  Publish: {panel_data.get('publish')}")

print("\n" + "="*80 + "\n")
