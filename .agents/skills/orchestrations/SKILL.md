---
name: orchestrations
description: Instructions for orchestrating new projects and K8s workspaces using control.py.
---

# Orchestrations Skill

When the user asks you to create a new project workspace, use the `projects/control.py` script.
This script automatically scaffolds a new FastAPI project, creates its Dockerfile, adds Kubernetes Deployment and Service manifests, registers it with `kustomization.yaml`, and dynamically adds a routing rule to the cluster's Ingress.

### Usage
Run the following command to spin up a new project:
```bash
python projects/control.py create <project-name> --port <unique-port>
```

### Steps to implement a new work package:
1. Run the `control.py` script as shown above.
2. Build the Docker image manually using standard `docker build` (e.g. `docker build -t firecrawl-<project-name>-api:latest projects/<project_name>`).
3. Apply the updated K8s manifests using `kubectl apply -k k8s/`.
4. The service will be immediately available through the central Ingress at `<project-name>.firecrawl.local`.
