from app.models.entities import ControllerDecision
from app.services.segmentation import NetworkSegmentation


class NetworkController:
    def __init__(self):
        self.segmentation = NetworkSegmentation()

    def analyze_nodes(self, nodes):
        decisions = []

        for node in nodes:
            load = node.get("load", 0)
            channel = node.get("channel", 1)

            if load >= 2:
                decisions.append(
                    ControllerDecision(
                        node_id=node["id"],
                        action="reduce_tx_power",
                        value="-1 dBm",
                        reason="high_load"
                    ).model_dump()
                )

            if load >= 3:
                new_channel = 11 if channel != 11 else 6
                decisions.append(
                    ControllerDecision(
                        node_id=node["id"],
                        action="change_channel",
                        value=str(new_channel),
                        reason="congestion_detected"
                    ).model_dump()
                )

        return decisions

    def evaluate_access(self, clients):
        access_results = []

        for client in clients:
            role = client.role
            targets = ["internet", "staff", "management", "controller"]

            for target in targets:
                allowed = self.segmentation.is_allowed(role, target)
                access_results.append({
                    "client_id": client.id,
                    "client_name": client.name,
                    "role": role,
                    "target_zone": target,
                    "allowed": allowed
                })

        return access_results