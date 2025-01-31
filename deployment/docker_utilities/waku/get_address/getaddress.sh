#!/bin/bash

# Number of addrs to process, default to 1 if not specified
num_addrs=${1:-1}

# Service name to query, default to "zerotesting-bootstrap.zerotesting" if not specified
service_name=${2:-zerotesting-bootstrap.zerotesting}

# Find the IPv4 IPs of "zerotesting-bootstrap.zerotesting" using nslookup
readarray -t pod_ips < <(nslookup "$service_name" | awk '/^Address: / { print $2 }' | head -n "$num_addrs")

# Prepare the directory for addrs data
mkdir -p /etc/addrs
addrs_file="/etc/addrs/addrs.env"
> "$addrs_file" # Clear the file to start fresh

# Function to validate addrs
validate_addrs() {
    if [[ $1 =~ ^/ip ]]; then
        return 0 # Valid
    else
        return 1 # Invalid
    fi
}

# Counter for valid addrs
valid_addrs_count=0

# Get and validate the addrs data from up to the specified number of IPs
for pod_ip in "${pod_ips[@]}"; do
    echo "Querying IP: $pod_ip"
    addrs=$(curl -X GET "http://$pod_ip:8645/debug/v1/info" -H "accept: application/json" | sed -n 's/.*"listenAddresses":\["\([^"]*\)".*/\1/p')

    # Validate the addrs
    validate_addrs "$addrs"
    if [ $? -eq 0 ]; then
        # Save the valid addrs to the file
        ((valid_addrs_count++))
        echo "export addrs$valid_addrs_count='$addrs'" >> "$addrs_file"
        if [ $valid_addrs_count -eq "$num_addrs" ]; then
            break # Exit loop after the specified number of valid addrs
        fi
    else
        echo "Invalid addrs data received from IP $pod_ip"
    fi
done

# Check if we got at least one valid addrs
if [ $valid_addrs_count -eq 0 ]; then
    echo "No valid addrs data received from any IPs"
    exit 1
fi

# Output for debugging
echo "addrs data saved successfully:"
cat "$addrs_file"
