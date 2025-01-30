#!/bin/bash

# Number of ENRs to process, default to 3 if not specified
num_enrs=${1:-3}

# Service name to query, default to "zerotesting-bootstrap.zerotesting" if not specified
service_name=${2:-zerotesting-bootstrap.zerotesting}

# Find the IPv4 IPs of "zerotesting-bootstrap.zerotesting" using nslookup
readarray -t pod_ips < <(nslookup "$service_name" | awk '/^Address: / { print $2 }' | head -n "$num_enrs")

# Shuffle the IPs before processing them to help randomise which nodes we connect to and peer with
# Disabled for now
#readarray -t pod_ips < <(printf "%s\n" "${pod_ips[@]}" | shuf)

# Prepare the directory for ENR data
mkdir -p /etc/enr
enr_file="/etc/enr/enr.env"
> "$enr_file" # Clear the file to start fresh

# Function to validate ENR
validate_enr() {
    if [[ $1 =~ ^enr:- ]]; then
        return 0 # Valid
    else
        return 1 # Invalid
    fi
}

# Counter for valid ENRs
valid_enr_count=0

# Get and validate the ENR data from up to the specified number of IPs
for pod_ip in "${pod_ips[@]}"; do
    echo "Querying IP: $pod_ip"
    enr=$(curl -X GET "http://$pod_ip:8645/debug/v1/info" -H "accept: application/json" | sed -n 's/.*"enrUri":"\([^"]*\)".*/\1/p')

    # Validate the ENR
    validate_enr "$enr"
    if [ $? -eq 0 ]; then
        # Save the valid ENR to the file
        ((valid_enr_count++))
        echo "export ENR$valid_enr_count='$enr'" >> "$enr_file"
        if [ $valid_enr_count -eq "$num_enrs" ]; then
            break # Exit loop after the specified number of valid ENRs
        fi
    else
        echo "Invalid ENR data received from IP $pod_ip"
    fi
done

# Check if we got at least one valid ENR
if [ $valid_enr_count -eq 0 ]; then
    echo "No valid ENR data received from any IPs"
    exit 1
fi

# Output for debugging
echo "ENR data saved successfully:"
cat "$enr_file"
