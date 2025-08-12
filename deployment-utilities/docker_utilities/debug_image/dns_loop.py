#!/usr/bin/env python3

import socket
import time
import argparse
from itertools import cycle

def dns_lookup(hostname, dns_servers):
    target_dns = next(dns_servers, None)  # Use default DNS if none provided
    try:
        # Set up a monkey patch only if specific DNS server is provided
        if target_dns:
            original_getaddrinfo = socket.getaddrinfo
            def getaddrinfo_monkeypatch(host, port, family=0, type=0, proto=0, flags=0):
                return original_getaddrinfo(host, port, family, socket.SOCK_DGRAM, proto, flags)
            socket.getaddrinfo = getaddrinfo_monkeypatch

        socket.setdefaulttimeout(10)  # Optional: Set a timeout for DNS requests
        ip_address = socket.gethostbyname(hostname)
        print(f"Successfully resolved {hostname} to {ip_address} using DNS server {target_dns or 'system default'}")
        return True
    except Exception as e:  # Broad exception to catch all possible errors
        print(f"Failed to resolve {hostname} using DNS server {target_dns or 'system default'}: {e}")
        return False
    finally:
        if target_dns:
            socket.getaddrinfo = original_getaddrinfo  # Restore original getaddrinfo

def main(dns_servers):
    dns_servers_cycle = cycle(dns_servers) if dns_servers else cycle([None])  # Cycle through provided DNS servers or use default
    success_count, fail_count = 0, 0  # Initialize counters

    while True:  # Loop indefinitely
        for i in range(args.nodes):
            hostname = f"nodes-{i}"
            if dns_lookup(hostname, dns_servers_cycle):
                success_count += 1
            else:
                fail_count += 1

            # Print counts every iteration to show progress
            print(f"Processed {i + 1}/{args.nodes} hostnames, Success: {success_count}, Failures: {fail_count}")
            time.sleep(args.delay)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform DNS lookups with specified target DNS server or system default")
    parser.add_argument("--target", help="IP address of the target DNS server", nargs='*', default=[])
    parser.add_argument("--accept-input", action="store_true", help="Accept a list of IP addresses from user input")
    parser.add_argument("--nodes", help="Number of nodes to resolve", type=int, default=1000)
    parser.add_argument("--delay", help="Delay in seconds", type=float, default=0.4)
    args = parser.parse_args()

    dns_servers = args.target
    if args.accept_input:
        input_servers = input("Enter DNS IP addresses (comma or space-separated): ").replace(',', ' ').split()
        dns_servers.extend(input_servers)
    
    # Check if there are no DNS servers provided and not using system default
    if not dns_servers:
        print("No specific DNS servers provided; using system default DNS settings.")
    
    main(dns_servers)

