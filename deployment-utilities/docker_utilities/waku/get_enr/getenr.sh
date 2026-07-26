#!/bin/bash

# Number of ENRs to process, default to 3 if not specified
num_enrs=${1:-3}

# Service name to query, default to "zerotesting-bootstrap.zerotesting" if not specified
service_name=${2:-zerotesting-bootstrap.zerotesting}

# Output file for the ENR data, default to "/etc/enr/ENR" if not specified
output_file=${3:-/etc/enr/ENR}

# Ensure the directory for the output file exists
mkdir -p "$(dirname "$output_file")"
> "$output_file" # Clear the file to start fresh

# Extract basename
base_name=$(basename "$output_file")

validate_enr() {
    if [[ $1 =~ ^enr:- ]]; then
        return 0 # Valid
    else
        return 1 # Invalid
    fi
}

# Find the IPv4 IPs of the service using nslookup
readarray -t pod_ips < <(nslookup "$service_name" | awk '/^Address: / { print $2 }' | head -n "$num_enrs")

valid_enr_count=0

# Get and validate the ENR data from up to the specified number of IPs
for pod_ip in "${pod_ips[@]}"; do
    echo "Querying IP: $pod_ip"
    enr=$(curl -X GET "http://$pod_ip:8645/debug/v1/info" -H "accept: application/json" | sed -n 's/.*"enrUri":"\([^"]*\)".*/\1/p')

    validate_enr "$enr"
    if [ $? -eq 0 ]; then
        ((valid_enr_count++))
        echo "export ${base_name}${valid_enr_count}='$enr'" >> "$output_file"
        if [ $valid_enr_count -eq "$num_enrs" ]; then
            break
        fi
    else
        echo "Invalid ENR data received from IP $pod_ip"
    fi
done

if [ $valid_enr_count -eq 0 ]; then
    echo "No valid ENR data received from any IPs"
    exit 1
fi

echo "ENR data saved successfully to $output_file:"
cat "$output_file"