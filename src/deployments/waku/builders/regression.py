class RegressionNodes:
    @staticmethod
    def create_args(cmd_type: int) -> dict:
        base = {
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
        }

        if cmd_type == 1:
            return {
                **base,
                "--cluster-id": 2,
                "--shard": 0,
            }
        elif cmd_type == 2:
            return {
                **base,
                "--num-shards-in-network": 1,
                "--shard": 0,
            }

        raise ValueError(f"Invalid cmd_type: `{cmd_type}`")
