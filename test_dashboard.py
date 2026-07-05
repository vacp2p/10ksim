#!/usr/bin/env python3
"""Test script to inspect database and test API endpoints."""

import requests
import json
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.config.utils import LoadConfig

def print_section(title):
    """Print section header."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def inspect_database():
    """Inspect what's stored in the database."""
    print_section("DATABASE INSPECTION")
    
    db = DSTDatabase()
    
    # Check datasources
    print("\n📊 DATASOURCES:")
    datasources = list(db.datasources.find({}))
    print(f"  Total: {len(datasources)}")
    for ds in datasources:
        print(f"  - {ds.get('name')} ({ds.get('type')}) - {ds.get('url')}")
    
    # Check experiments
    print("\n🔬 EXPERIMENTS:")
    experiments = list(db.experiments.find({}))
    print(f"  Total: {len(experiments)}")
    for exp in experiments:
        print(f"  - ID: {exp.get('id')}")
        print(f"    Title: {exp.get('title')}")
        print(f"    Datasets: {len(exp.get('datasets', []))}")
        print(f"    Panels: {len(exp.get('panels', []))}")
    
    # Check datasets
    print("\n📁 DATASETS:")
    datasets = list(db.datasets.find({}))
    print(f"  Total: {len(datasets)}")
    for ds in datasets:
        data = ds.get('data', [])
        print(f"  - {ds.get('experiment_id')}:{ds.get('dataset_name')}")
        print(f"    Rows: {len(data)}")
        if data:
            print(f"    Sample row: {json.dumps(data[0], indent=6, default=str)}")
            print(f"    Fields: {list(data[0].keys())}")
    
    # Check panels
    print("\n📈 PANELS:")
    panels = list(db.panels.find({}))
    print(f"  Total: {len(panels)}")
    for panel in panels:
        print(f"  - {panel.get('experiment_id')}:{panel.get('name')}")
        print(f"    Type: {panel.get('type')}")
        print(f"    Dataset: {panel.get('dataset')}")

def test_api_endpoints():
    """Test API endpoints."""
    print_section("API ENDPOINT TESTS")
    
    base_url = "http://localhost:8000"
    
    # Test datasources
    print("\n🔌 GET /datasources")
    response = requests.get(f"{base_url}/datasources")
    print(f"  Status: {response.status_code}")
    if response.ok:
        data = response.json()
        print(f"  Count: {len(data)}")
        for ds in data:
            print(f"  - {ds['name']} ({ds['type']})")
    
    # Test experiments
    print("\n🔬 GET /experiments")
    response = requests.get(f"{base_url}/experiments")
    print(f"  Status: {response.status_code}")
    if response.ok:
        experiments = response.json()
        print(f"  Count: {len(experiments)}")
        
        # Test each experiment's datasets
        for exp in experiments:
            exp_id = exp['id']
            print(f"\n  📊 Experiment: {exp_id}")
            
            # Get datasets for this experiment
            for dataset in exp.get('datasets', []):
                dataset_name = dataset['name']
                print(f"\n    📁 Dataset: {dataset_name}")
                
                # Get dataset config
                response = requests.get(
                    f"{base_url}/experiments/{exp_id}/datasets/{dataset_name}"
                )
                print(f"      Config status: {response.status_code}")
                if response.ok:
                    config = response.json()
                    print(f"      Datasource: {config['datasource']}")
                    print(f"      Schema fields: {[f['name'] for f in config.get('schema', [])]}")
                
                # Get dataset data
                response = requests.get(
                    f"{base_url}/experiments/{exp_id}/datasets/{dataset_name}/data"
                )
                print(f"      Data status: {response.status_code}")
                if response.ok:
                    result = response.json()
                    data = result.get('data', [])
                    source = result.get('source', 'unknown')
                    print(f"      Rows: {len(data)} (from {source})")
                    if data:
                        print(f"      Sample row: {json.dumps(data[0], indent=10, default=str)}")
                        print(f"      Fields: {list(data[0].keys())}")
                else:
                    print(f"      Error: {response.text}")

def main():
    """Run all tests."""
    print("\n" + "🚀 DST Dashboard Test Suite ".center(80, "="))
    
    try:
        inspect_database()
        test_api_endpoints()
        
        print("\n" + "✅ Test Complete ".center(80, "=") + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
