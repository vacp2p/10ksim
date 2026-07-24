from src.analysis.mesh_analysis.readers.tracers.service_discovery_tracer import ServiceDiscoveryTracer


def test_extract_found_peer_discovery_time_keeps_first_discovery_per_peer_and_service():
    tracer = ServiceDiscoveryTracer()
    parsed_logs = [
        ("2026-07-02 15:51:36.000+00:00", "peer-a", "service-1"),
        ("2026-07-02 15:51:35.000+00:00", "peer-a", "service-1"),
        ("2026-07-02 15:51:34.000+00:00", "peer-a", "service-2"),
        ("2026-07-02 15:51:33.000+00:00", "peer-b", "service-1"),
        ("2026-07-02 15:51:37.000+00:00", "peer-b", "service-1"),
    ]

    result = tracer._extract_found_peer_discovery_time(parsed_logs)

    assert result[["peerId", "serviceId"]].values.tolist() == [
        ["peer-b", "service-1"],
        ["peer-a", "service-2"],
        ["peer-a", "service-1"],
    ]
    assert result["found_time"].dt.strftime("%H:%M:%S").tolist() == [
        "15:51:33",
        "15:51:34",
        "15:51:35",
    ]
