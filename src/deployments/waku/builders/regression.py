class RegressionNodes:
    @staticmethod
    def create_args() -> dict:
        return {
            "--cluster-id": 2,
            "--discv5-discovery": True,
            "--discv5-enr-auto-update": True,
            "--log-level": "INFO",
            "--max-connections": 200,
            "--metrics-server-address": "0.0.0.0",
            "--metrics-server": True,
            "--nat": "extip:${IP}",
            "--relay": True,
            "--rest-address": "0.0.0.0",
            "--rest-admin": True,
            "--rest": True,
            "--shard": 0,
        }
