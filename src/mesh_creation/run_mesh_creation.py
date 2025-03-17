# Python Imports
import logging

# Project Imports
import src.logger.logger
from mesh_manager import MeshManager
from protocols.waku_protocol import WakuProtocol
from protocols.libp2p_protocol import LibP2PProtocol

logger = logging.getLogger("src.mesh_creation.run_mesh_creation")

def main():
    logger.info("Starting mesh creation process")
    mesh_manager = MeshManager(
        kube_config="rubi3.yaml",
        namespace="zerotesting"
    )

    # Example 1: Create mesh with different protocols and topology configs for each StatefulSet
    statefulset_configs = [
        # First StatefulSet with Waku protocol and custom topology
        ("nodes.yaml", {
            "type": "libp2p_custom",
            "parameters": {
                "n": 10,
                "d_low": 4,
                "d_high": 6
            }
        }, WakuProtocol(port=8645)),
        
        ## Second StatefulSet with LibP2P protocol and random topology
        #("statefulset2.yaml", {
        #    "type": "random",
        #    "parameters": {
        #        "n": 3,
        #        "p": 0.5
        #    }
        #}, LibP2PProtocol(port=8080))
    ]
    
    logger.info("Creating mesh with configurations: %s", statefulset_configs)
    mesh_manager.create_mesh(statefulset_configs)
    logger.info("Mesh creation completed")


    # Example 3: Create mesh from Pajek files with different protocols
    # pajek_configs = [
    #     ("statefulset1.yaml", "topology1.net", WakuProtocol(port=8645)),
    #     ("statefulset2.yaml", "topology2.net", LibP2PProtocol(port=8080))
    # ]
    # mesh_manager.create_mesh_from_pajek_files(pajek_configs)

if __name__ == "__main__":
    main()
