#!/bin/bash

# Define the range of pod numbers
pod_range=({0..149})

# Iterate through each pod in the range
for pod_number in "${pod_range[@]}"; do
    # Formulate the pod name
    pod_name="pod-$pod_number"

    # Formulate the output filename based on pod and container
    output_file="logs_${pod_name}.txt"
    # Redirect logs to the file
    sudo kubectl logs -n 10k-namespace -c "$container_name" "$pod_name" > "logs/$output_file"

    echo "Logs for $pod_name saved to $output_file"
done

