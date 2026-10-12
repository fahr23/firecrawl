#!/usr/bin/env python3
import argparse
import os
import re

def create_project(name, port):
    safe_name = name.lower().replace("-", "_").replace(" ", "_")
    k8s_name = name.lower().replace("_", "-")
    
    os.makedirs(f"projects/{safe_name}", exist_ok=True)
    print(f"Created directory projects/{safe_name}")
    
    # 1. Scaffold basic FastAPI app
    with open(f"projects/{safe_name}/main.py", "w") as f:
        f.write(f"""from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/")\ndef read_root():\n    return {{"status": "ok", "project": "{name}"}}\n""")
    
    with open(f"projects/{safe_name}/requirements.runtime.txt", "w") as f:
        f.write("fastapi\nuvicorn\n")
        
    with open(f"projects/{safe_name}/Dockerfile", "w") as f:
        f.write(f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.runtime.txt .
RUN pip install -r requirements.runtime.txt
COPY . .
EXPOSE {port}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
""")

    # 2. Add K8s manifest
    k8s_file = f"k8s/25-{k8s_name}.yaml"
    with open(k8s_file, "w") as f:
        f.write(f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {k8s_name}-api
  namespace: firecrawl
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {k8s_name}-api
  template:
    metadata:
      labels:
        app: {k8s_name}-api
    spec:
      containers:
      - name: api
        image: firecrawl-{k8s_name}-api:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: {port}
---
apiVersion: v1
kind: Service
metadata:
  name: {k8s_name}-api
  namespace: firecrawl
spec:
  type: ClusterIP
  ports:
  - port: {port}
    targetPort: {port}
  selector:
    app: {k8s_name}-api
""")
    
    # 3. Add to kustomization.yaml
    with open("k8s/kustomization.yaml", "r") as f:
        kustomize = f.read()
    if f"25-{k8s_name}.yaml" not in kustomize:
        kustomize = kustomize.replace("resources:", f"resources:\n- 25-{k8s_name}.yaml")
        with open("k8s/kustomization.yaml", "w") as f:
            f.write(kustomize)
            
    # 4. Add to Ingress
    ingress_rule = f"""
  - host: {k8s_name}.localhost
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {k8s_name}-api
            port:
              number: {port}"""
    
    with open("k8s/40-ingress.yaml", "r") as f:
        ingress = f.read()
    if f"host: {k8s_name}.localhost" not in ingress:
        # Add to TLS hosts
        ingress = re.sub(r'(secretName: firecrawl-tls)', r'- ' + k8s_name + r'.localhost
    ', ingress)
        # Append rule to rules section
        ingress = ingress + ingress_rule
        with open("k8s/40-ingress.yaml", "w") as f:
            f.write(ingress)
            
    print(f"Successfully scaffolded {name} on port {port}. Available at {k8s_name}.localhost!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create"])
    parser.add_argument("name", help="Name of the project/workspace")
    parser.add_argument("--port", type=int, default=8020, help="Port for the service")
    args = parser.parse_args()
    
    if args.action == "create":
        create_project(args.name, args.port)
