# GKE Migration & Auto-Scaling Plan

This plan outlines the steps to migrate the deployment to Google Kubernetes Engine (GKE) and implement auto-scaling using the unified `log-web` application.

## User Review Required
> [!IMPORTANT]
> This migration switches from simple VMs (GCE) to a Managed Kubernetes Cluster (GKE). Ensure you have sufficient quota (CPUs/IPs) in your GCP project.
> We are unifying logic: `log-web` will be used for BOTH manual control (Web UI) and auto-scaled background generation.

## Proposed Changes

### Application Logic (Auto-Start)

#### [MODIFY] [src/webload/app.py](file:///c:/Users/thanh.nt4/Documents/code/log-analytics-project/src/webload/app.py)
- Add `AUTO_START` environment variable support.
- If `AUTO_START=true`, automatically trigger `_run_scenario` on startup (using "baseline" or configured scenario).
- This allows HPA (Horizontal Pod Autoscaler) to spin up new pods that immediately start working.

### Deployment Script

#### [MODIFY] [scripts/deploy-gke.sh](file:///c:/Users/thanh.nt4/Documents/code/log-analytics-project/scripts/deploy-gke.sh)
- Change Docker build source for producer: `src/producer/` -> `src/webload/`.
- Change image name/tag logic to ensure consistency.

### Kubernetes Manifests

#### [MODIFY] [k8s/producer/deployment.yaml](file:///c:/Users/thanh.nt4/Documents/code/log-analytics-project/k8s/producer/deployment.yaml)
- **Container Port**: Change 8000 -> 8088.
- **Image**: Ensure it points to the new `log-web` image.
- **Env Vars**: Add `AUTO_START: "true"` (since this deployment is for the HPA scaler).
- **Probes**: Update health check ports to 8088.
- **Annotations**: Update `prometheus.io/port` to "8088".

#### [MODIFY] [k8s/hpa/log-producer-hpa.yaml](file:///c:/Users/thanh.nt4/Documents/code/log-analytics-project/k8s/hpa/log-producer-hpa.yaml)
- Use standard HPA (v2beta2 or v1) targeting the `log-producer` deployment (which now runs `log-web` code).

## Verification Plan

### Automated Tests
- None.

### Manual Verification
1.  Run `./scripts/deploy-gke.sh`.
2.  **Verify UI**:
    -   Get Load Balancer IP (if exposed) or Port Forward to one pod to check UI.
3.  **Verify Scaling**:
    -   Generate load.
    -   `kubectl get hpa` -> Watch replica count increase.
    -   `kubectl get pods` -> See new pods appearing.
    -   Grafana -> See "Logs/sec" increase significantly.
