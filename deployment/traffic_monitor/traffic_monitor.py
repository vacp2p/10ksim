import time
import logging
from threading import Thread, Lock
from scapy.all import sniff, IP, TCP, UDP
from prometheus_client import start_http_server, Counter, Gauge
import socket
import argparse
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_metrics(ports):
    bytes_tcp_in = {}
    bytes_tcp_out = {}
    bytes_udp_in = {}
    bytes_udp_out = {}
    bytes_total_in = {}
    bytes_total_out = {}

    # Overall metrics for all ports combined
    bytes_overall_in = Counter('network_bytes_overall_in_total', 'Total incoming bytes across all ports')
    bytes_overall_out = Counter('network_bytes_overall_out_total', 'Total outgoing bytes across all ports')

    for port in ports:
        # Primary metrics
        bytes_total_in[port] = Counter(f'network_bytes_in_total_port_{port}', f'Total incoming bytes on port {port}')
        bytes_total_out[port] = Counter(f'network_bytes_out_total_port_{port}', f'Total outgoing bytes on port {port}')

        # Secondary, optional metrics
        bytes_tcp_in[port] = Counter(f'network_bytes_in_total_port_{port}_tcp', f'Total TCP incoming bytes on port {port}')
        bytes_tcp_out[port] = Counter(f'network_bytes_out_total_port_{port}_tcp', f'Total TCP outgoing bytes on port {port}')
        bytes_udp_in[port] = Counter(f'network_bytes_in_total_port_{port}_udp', f'Total UDP incoming bytes on port {port}')
        bytes_udp_out[port] = Counter(f'network_bytes_out_total_port_{port}_udp', f'Total UDP outgoing bytes on port {port}')

    return (bytes_tcp_in, bytes_tcp_out, bytes_udp_in, bytes_udp_out, 
            bytes_total_in, bytes_total_out, bytes_overall_in, bytes_overall_out)


PORTS = {}

class Stats:
    def __init__(self):
        self.lock = Lock()
        self.tcp_in = {port: 0 for port in PORTS}
        self.tcp_out = {port: 0 for port in PORTS}
        self.udp_in = {port: 0 for port in PORTS}
        self.udp_out = {port: 0 for port in PORTS}
        self.last_log = time.time()
        self.prometheus_udp_in = {port: 0 for port in PORTS}
        self.prometheus_udp_out = {port: 0 for port in PORTS}
        self.prometheus_total_in = {port: 0 for port in PORTS}
        self.prometheus_total_out = {port: 0 for port in PORTS}
        self.prometheus_overall_in = 0
        self.prometheus_overall_out = 0

def packet_callback(packet):
    if IP not in packet:
        return
        
    packet_length = len(packet)
    src_ip = packet[IP].src
    dst_ip = packet[IP].dst

    if UDP in packet:
        src_port = packet[UDP].sport
        dst_port = packet[UDP].dport
        
        with stats.lock:
            # If either IP is our pod IP
            if src_ip == pod_ip or dst_ip == pod_ip:
                if src_ip == pod_ip and src_port in PORTS:  # Outgoing
                    stats.udp_out[src_port] += packet_length
                    stats.prometheus_udp_out[src_port] += packet_length
                    stats.prometheus_total_out[src_port] += packet_length
                    stats.prometheus_overall_out += packet_length
                elif dst_ip == pod_ip and dst_port in PORTS:  # Incoming
                    stats.udp_in[dst_port] += packet_length
                    stats.prometheus_udp_in[dst_port] += packet_length
                    stats.prometheus_total_in[dst_port] += packet_length
                    stats.prometheus_overall_in += packet_length
            # If neither IP is our pod IP but involves our ports, it's outgoing
            else:
                if src_port in PORTS:
                    stats.udp_out[src_port] += packet_length
                    stats.prometheus_udp_out[src_port] += packet_length
                    stats.prometheus_total_out[src_port] += packet_length
                    stats.prometheus_overall_out += packet_length
                if dst_port in PORTS:
                    stats.udp_out[dst_port] += packet_length
                    stats.prometheus_udp_out[dst_port] += packet_length
                    stats.prometheus_total_out[dst_port] += packet_length
                    stats.prometheus_overall_out += packet_length

    elif TCP in packet:
        src_port = packet[TCP].sport
        dst_port = packet[TCP].dport
        
        with stats.lock:
            # If either IP is our pod IP
            if src_ip == pod_ip or dst_ip == pod_ip:
                if src_ip == pod_ip and src_port in PORTS:  # Outgoing
                    stats.tcp_out[src_port] += packet_length
                    stats.prometheus_tcp_out[src_port] += packet_length
                    stats.prometheus_total_out[src_port] += packet_length
                    stats.prometheus_overall_out += packet_length
                elif dst_ip == pod_ip and dst_port in PORTS:  # Incoming
                    stats.tcp_in[dst_port] += packet_length
                    stats.prometheus_tcp_in[dst_port] += packet_length
                    stats.prometheus_total_in[dst_port] += packet_length
                    stats.prometheus_overall_in += packet_length
            # If neither IP is our pod IP but involves our ports, it's outgoing
            else:
                if src_port in PORTS:
                    stats.tcp_out[src_port] += packet_length
                    stats.prometheus_tcp_out[src_port] += packet_length
                    stats.prometheus_total_out[src_port] += packet_length
                    stats.prometheus_overall_out += packet_length
                if dst_port in PORTS:
                    stats.tcp_out[dst_port] += packet_length
                    stats.prometheus_tcp_out[dst_port] += packet_length
                    stats.prometheus_total_out[dst_port] += packet_length
                    stats.prometheus_overall_out += packet_length

def log_stats():
    while True:
        time.sleep(5)
        now = time.time()
        
        with stats.lock:
            elapsed = now - stats.last_log
            
            # Calculate totals across all ports
            total_in = sum(stats.tcp_in[port] + stats.udp_in[port] for port in PORTS)
            total_out = sum(stats.tcp_out[port] + stats.udp_out[port] for port in PORTS)
            
            # Calculate rates
            total_in_rate = total_in / elapsed if elapsed > 0 else 0
            total_out_rate = total_out / elapsed if elapsed > 0 else 0
            
            logger.info(f"Overall Total In: {total_in_rate:.2f} B/s, Overall Total Out: {total_out_rate:.2f} B/s")
            
            for port, name in PORTS.items():
                tcp_in_rate = stats.tcp_in[port] / elapsed if elapsed > 0 else 0
                tcp_out_rate = stats.tcp_out[port] / elapsed if elapsed > 0 else 0
                udp_in_rate = stats.udp_in[port] / elapsed if elapsed > 0 else 0
                udp_out_rate = stats.udp_out[port] / elapsed if elapsed > 0 else 0
                total_in_rate = tcp_in_rate + udp_in_rate
                total_out_rate = tcp_out_rate + udp_out_rate
                
                logger.info(f"Port {name} - "
                          f"Total In: {total_in_rate:.2f} B/s, Total Out: {total_out_rate:.2f} B/s, "
                          f"TCP In: {tcp_in_rate:.2f} B/s, TCP Out: {tcp_out_rate:.2f} B/s, "
                          f"UDP In: {udp_in_rate:.2f} B/s, UDP Out: {udp_out_rate:.2f} B/s")
                
                # Reset counters
                stats.tcp_in[port] = 0
                stats.tcp_out[port] = 0
                stats.udp_in[port] = 0
                stats.udp_out[port] = 0
            
            stats.last_log = now

def update_prometheus_metrics():
    while True:
        time.sleep(5)  # Update prometheus metrics every 5 seconds
        
        with stats.lock:
            # Update all prometheus counters
            for port in PORTS:
                BYTES_TCP_IN[port].inc(stats.prometheus_tcp_in[port])
                BYTES_TCP_OUT[port].inc(stats.prometheus_tcp_out[port])
                BYTES_UDP_IN[port].inc(stats.prometheus_udp_in[port])
                BYTES_UDP_OUT[port].inc(stats.prometheus_udp_out[port])
                BYTES_TOTAL_IN[port].inc(stats.prometheus_tcp_in[port] + stats.prometheus_udp_in[port])
                BYTES_TOTAL_OUT[port].inc(stats.prometheus_tcp_out[port] + stats.prometheus_udp_out[port])
                
                # Reset prometheus accumulators
                stats.prometheus_tcp_in[port] = 0
                stats.prometheus_tcp_out[port] = 0
                stats.prometheus_udp_in[port] = 0
                stats.prometheus_udp_out[port] = 0
                stats.prometheus_total_in[port] = 0
                stats.prometheus_total_out[port] = 0
            
            # Update overall metrics
            BYTES_OVERALL_IN.inc(stats.prometheus_overall_in)
            BYTES_OVERALL_OUT.inc(stats.prometheus_overall_out)
            stats.prometheus_overall_in = 0
            stats.prometheus_overall_out = 0

class PodIPDetectionError(Exception):
    """Raised when pod IP detection fails"""
    pass

def detect_pod_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        pod_ip = s.getsockname()[0]
        logger.info(f"Detected pod IP: {pod_ip}")
        return pod_ip
    except Exception as e:
        logger.error(f"Failed to detect pod IP: {e}")
        raise PodIPDetectionError(f"Could not detect pod IP: {str(e)}")
    finally:
        s.close()

def main():
    parser = argparse.ArgumentParser(description='Monitor network traffic on specified ports')
    parser.add_argument('--ports', type=int, nargs='+', required=True,
                       help='List of ports to monitor')
    args = parser.parse_args()
    
    # Get pod IP (shared by all containers in pod)
    global pod_ip
    try:
        pod_ip = detect_pod_ip()
    except PodIPDetectionError as e:
        logger.error(e)
        sys.exit(1)
    
    # Setup metrics with provided ports
    global BYTES_TCP_IN, BYTES_TCP_OUT, BYTES_UDP_IN, BYTES_UDP_OUT, BYTES_TOTAL_IN, BYTES_TOTAL_OUT, BYTES_OVERALL_IN, BYTES_OVERALL_OUT
    global PORTS
    
    PORTS = {port: str(port) for port in args.ports}
    
    (BYTES_TCP_IN, BYTES_TCP_OUT, BYTES_UDP_IN, BYTES_UDP_OUT, 
     BYTES_TOTAL_IN, BYTES_TOTAL_OUT, BYTES_OVERALL_IN, BYTES_OVERALL_OUT) = setup_metrics(args.ports)
    
    global stats
    stats = Stats()
    
    # Start Prometheus HTTP server
    start_http_server(8009)
    logger.info("Started Prometheus metrics server on port 8009")
    
    # Start prometheus metrics update thread
    Thread(target=update_prometheus_metrics, daemon=True).start()
    
    # Start stats logging thread
    Thread(target=log_stats, daemon=True).start()
    
    # Start packet capture
    ports_str = ', '.join(map(str, args.ports))
    logger.info(f"Starting packet capture for ports: {ports_str}...")
    sniff(prn=packet_callback, store=0)

if __name__ == "__main__":
    main()