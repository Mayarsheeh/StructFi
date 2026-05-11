from app.models.entities import SecurityAlert


class SecurityEngine:
    def __init__(self):
        self.alert_counter = 1

    def build_alert(self, severity, title, description, node_id=None, client_id=None):
        alert = SecurityAlert(
            id=self.alert_counter,
            severity=severity,
            title=title,
            description=description,
            node_id=node_id,
            client_id=client_id
        )
        self.alert_counter += 1
        return alert.model_dump()

    def analyze_access_matrix(self, access_matrix):
        alerts = []

        for item in access_matrix:
            role = item["role"]
            target = item["target_zone"]
            allowed = item["allowed"]

            if role == "guest" and target in ["management", "controller"] and not allowed:
                alerts.append(
                    self.build_alert(
                        severity="critical",
                        title="Guest Isolation Enforcement",
                        description=f'{item["client_name"]} is blocked from accessing {target}.',
                        client_id=item["client_id"]
                    )
                )

            elif role == "staff" and target == "management" and not allowed:
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Staff Restricted Access",
                        description=f'{item["client_name"]} is not allowed to access management zone.',
                        client_id=item["client_id"]
                    )
                )

        return alerts

    def analyze_node_health(self, nodes):
        alerts = []

        for node in nodes:
            if node.get("status") == "down":
                alerts.append(
                    self.build_alert(
                        severity="critical",
                        title="Node Down",
                        description=f'{node["name"]} is offline.',
                        node_id=node["id"]
                    )
                )

            elif node.get("status") == "degraded":
                alerts.append(
                    self.build_alert(
                        severity="warning",
                        title="Node Degraded",
                        description=f'{node["name"]} is running in degraded mode.',
                        node_id=node["id"]
                    )
                )

            elif node.get("load", 0) >= 3:
                alerts.append(
                    self.build_alert(
                        severity="info",
                        title="High Node Load",
                        description=f'{node["name"]} is serving many clients.',
                        node_id=node["id"]
                    )
                )

        return alerts