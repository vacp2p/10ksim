import time
import logging
from threading import Thread
from scapy.all import sniff, IP, TCP, UDP
from prometheus_client import start_http_server, Counter, Gauge
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Port definitions
PORTS = {
    8545: "json-rpc",
    9000: "discv5",
    60000: "libp2p"
}

# Prometheus metrics setup
BYTES_TCP_IN = {}
BYTES_TCP_OUT = {}
BYTES_UDP_IN = {}
BYTES_UDP_OUT = {}
BYTES_TOTAL_IN = {}
BYTES_TOTAL_OUT = {}
RATE_TCP_IN = {}
RATE_TCP_OUT = {}
RATE_UDP_IN = {}
RATE_UDP_OUT = {}
RATE_TOTAL_IN = {}
RATE_TOTAL_OUT = {}

for port, name in PORTS.items():
    BYTES_TCP_IN[port] = Counter(f'network_tcp_bytes_in_total_port_{port}', f'Total TCP incoming bytes on port {port}')
    BYTES_TCP_OUT[port] = Counter(f'network_tcp_bytes_out_total_port_{port}', f'Total TCP outgoing bytes on port {port}')
    BYTES_UDP_IN[port] = Counter(f'network_udp_bytes_in_total_port_{port}', f'Total UDP incoming bytes on port {port}')
    BYTES_UDP_OUT[port] = Counter(f'network_udp_bytes_out_total_port_{port}', f'Total UDP outgoing bytes on port {port}')
    BYTES_TOTAL_IN[port] = Counter(f'network_bytes_in_total_port_{port}', f'Total incoming bytes on port {port}')
    BYTES_TOTAL_OUT[port] = Counter(f'network_bytes_out_total_port_{port}', f'Total outgoing bytes on port {port}')
    RATE_TCP_IN[port] = Gauge(f'network_tcp_bytes_in_per_second_port_{port}', f'TCP incoming bytes per second on port {port}')
    RATE_TCP_OUT[port] = Gauge(f'network_tcp_bytes_out_per_second_port_{port}', f'TCP outgoing bytes per second on port {port}')
    RATE_UDP_IN[port] = Gauge(f'network_udp_bytes_in_per_second_port_{port}', f'UDP incoming bytes per second on port {port}')
    RATE_UDP_OUT[port] = Gauge(f'network_udp_bytes_out_per_second_port_{port}', f'UDP outgoing bytes per second on port {port}')
    RATE_TOTAL_IN[port] = Gauge(f'network_bytes_in_per_second_port_{port}', f'Total incoming bytes per second on port {port}')
    RATE_TOTAL_OUT[port] = Gauge(f'network_bytes_out_per_second_port_{port}', f'Total outgoing bytes per second on port {port}')

class Stats:
    def __init__(self):
        self.tcp_in = {port: 0 for port in PORTS}
        self.tcp_out = {port: 0 for port in PORTS}
        self.udp_in = {port: 0 for port in PORTS}
        self.udp_out = {port: 0 for port in PORTS}
        self.last_log = time.time()

stats = Stats()

def packet_callback(packet):
    if IP not in packet:
        return
        
    # Get pod IP (shared by all containers in pod)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        pod_ip = s.getsockname()[0]
    except Exception:
        return
    finally:
        s.close()

    packet_length = len(packet)
    src_ip = packet[IP].src
    dst_ip = packet[IP].dst

    if UDP in packet:
        src_port = packet[UDP].sport
        dst_port = packet[UDP].dport
        
        # If either IP is our pod IP
        if src_ip == pod_ip or dst_ip == pod_ip:
            if src_ip == pod_ip and src_port in PORTS:  # Outgoing
                stats.udp_out[src_port] += packet_length
                BYTES_UDP_OUT[src_port].inc(packet_length)
                BYTES_TOTAL_OUT[src_port].inc(packet_length)
            elif dst_ip == pod_ip and dst_port in PORTS:  # Incoming
                stats.udp_in[dst_port] += packet_length
                BYTES_UDP_IN[dst_port].inc(packet_length)
                BYTES_TOTAL_IN[dst_port].inc(packet_length)
        # If neither IP is our pod IP but involves our ports, it's outgoing
        else:
            if src_port in PORTS:
                stats.udp_out[src_port] += packet_length
                BYTES_UDP_OUT[src_port].inc(packet_length)
                BYTES_TOTAL_OUT[src_port].inc(packet_length)
            if dst_port in PORTS:
                stats.udp_out[dst_port] += packet_length
                BYTES_UDP_OUT[dst_port].inc(packet_length)
                BYTES_TOTAL_OUT[dst_port].inc(packet_length)

    elif TCP in packet:
        src_port = packet[TCP].sport
        dst_port = packet[TCP].dport
        
        # If either IP is our pod IP
        if src_ip == pod_ip or dst_ip == pod_ip:
            if src_ip == pod_ip and src_port in PORTS:  # Outgoing
                stats.tcp_out[src_port] += packet_length
                BYTES_TCP_OUT[src_port].inc(packet_length)
                BYTES_TOTAL_OUT[src_port].inc(packet_length)
            elif dst_ip == pod_ip and dst_port in PORTS:  # Incoming
                stats.tcp_in[dst_port] += packet_length
                BYTES_TCP_IN[dst_port].inc(packet_length)
                BYTES_TOTAL_IN[dst_port].inc(packet_length)
        # If neither IP is our pod IP but involves our ports, it's outgoing
        else:
            if src_port in PORTS:
                stats.tcp_out[src_port] += packet_length
                BYTES_TCP_OUT[src_port].inc(packet_length)
                BYTES_TOTAL_OUT[src_port].inc(packet_length)
            if dst_port in PORTS:
                stats.tcp_out[dst_port] += packet_length
                BYTES_TCP_OUT[dst_port].inc(packet_length)
                BYTES_TOTAL_OUT[dst_port].inc(packet_length)

def log_stats():
    while True:
        time.sleep(2)
        now = time.time()
        elapsed = now - stats.last_log
        
        for port, name in PORTS.items():
            tcp_in_rate = stats.tcp_in[port] / elapsed if elapsed > 0 else 0
            tcp_out_rate = stats.tcp_out[port] / elapsed if elapsed > 0 else 0
            udp_in_rate = stats.udp_in[port] / elapsed if elapsed > 0 else 0
            udp_out_rate = stats.udp_out[port] / elapsed if elapsed > 0 else 0
            total_in_rate = tcp_in_rate + udp_in_rate
            total_out_rate = tcp_out_rate + udp_out_rate
            
            logger.info(f"{name} (:{port}) - "
                      f"Total In: {total_in_rate:.2f} B/s, Total Out: {total_out_rate:.2f} B/s, "
                      f"TCP In: {tcp_in_rate:.2f} B/s, TCP Out: {tcp_out_rate:.2f} B/s, "
                      f"UDP In: {udp_in_rate:.2f} B/s, UDP Out: {udp_out_rate:.2f} B/s")
            
            # Update Prometheus gauges
            RATE_TCP_IN[port].set(tcp_in_rate)
            RATE_TCP_OUT[port].set(tcp_out_rate)
            RATE_UDP_IN[port].set(udp_in_rate)
            RATE_UDP_OUT[port].set(udp_out_rate)
            RATE_TOTAL_IN[port].set(total_in_rate)
            RATE_TOTAL_OUT[port].set(total_out_rate)
            
            # Reset counters
            stats.tcp_in[port] = 0
            stats.tcp_out[port] = 0
            stats.udp_in[port] = 0
            stats.udp_out[port] = 0
        
        stats.last_log = now

def main():
    # Start Prometheus HTTP server
    start_http_server(8009)
    logger.info("Started Prometheus metrics server on port 8009")
    
    # Start stats logging thread
    Thread(target=log_stats, daemon=True).start()
    
    # Start packet capture
    logger.info("Starting packet capture for ports 8545, 9000, and 60000...")
    sniff(prn=packet_callback, store=0)

if __name__ == "__main__":
    main() 