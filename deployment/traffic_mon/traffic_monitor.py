from scapy.all import sniff, IP
from prometheus_client import start_http_server, Counter, Gauge
import time

# Prometheus metrics
BYTES_IN_TOTAL = Counter('network_bytes_in_total', 'Total incoming bytes on port 8545')
BYTES_OUT_TOTAL = Counter('network_bytes_out_total', 'Total outgoing bytes on port 8545')
BYTES_IN_PER_SECOND = Gauge('network_bytes_in_per_second', 'Incoming bytes per second on port 8545')
BYTES_OUT_PER_SECOND = Gauge('network_bytes_out_per_second', 'Outgoing bytes per second on port 8545')

def packet_callback(packet):
    if IP in packet:
        packet_length = len(packet)
        # Check if the packet is incoming or outgoing based on destination port
        if packet[IP].dport == 8545:
            # Incoming traffic
            BYTES_IN_TOTAL.inc(packet_length)
            BYTES_IN_PER_SECOND.set(packet_length)
        elif packet[IP].sport == 8545:
            # Outgoing traffic
            BYTES_OUT_TOTAL.inc(packet_length)
            BYTES_OUT_PER_SECOND.set(packet_length)

def main():
    # Start Prometheus HTTP server
    start_http_server(8009)
    
    # Start packet capture
    sniff(
        filter="port 8545",
        prn=packet_callback,
        store=0  # Don't store packets in memory
    )

if __name__ == "__main__":
    main()