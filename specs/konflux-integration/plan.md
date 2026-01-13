# Implementation Plan: Konflux Integration Test Scenario

**Branch**: `konflux-integration` | **Date**: 2026-01-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/konflux-integration/spec.md`

## Summary

Enable opendatahub-tests to run as an **IntegrationTestScenario (ITS)** in existing Konflux component build pipelines. When a component is built, the Konflux Integration Service triggers the ITS pipeline which provisions an ephemeral HyperShift cluster, installs ODH with SNAPSHOT component images, runs smoke tests, and reports results back to Konflux.

**Important**: Due to Konflux EaaS GPU limitations, a **hybrid architecture** is required. Non-GPU tests run on ephemeral clusters via ITS (Path A), while GPU tests run on a dedicated persistent cluster (Path B).

## Technical Context

**Language/Version**: Python 3.13 (existing tests), YAML (Tekton pipelines, Kubernetes resources)
**Primary Dependencies**: Tekton Pipelines v1, Konflux EaaS StepActions, pytest, openshift-python-wrapper
**Storage**: Konflux artifact storage for test results and must-gather
**Testing**: pytest with existing test infrastructure
**Target Platform**: Konflux-managed ephemeral HyperShift clusters on AWS
**Project Type**: CI/CD pipeline integration (IntegrationTestScenario)
**Performance Goals**: Total ITS execution <45 min (including ~15 min cluster provisioning)
**Constraints**: SNAPSHOT parameter required, ephemeral cluster lifecycle, **no GPU support on EaaS** (see Hybrid Architecture)
**Scale/Scope**: Non-GPU smoke tests on ITS (~50 tests), GPU tests on dedicated cluster

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First | ✅ PASS | Using Konflux-native patterns (EaaS StepActions, git resolver) |
| II. Code Consistency | ✅ PASS | Following Konflux pipeline-samples patterns |
| III. Test Independence | ✅ PASS | Each ITS run gets isolated ephemeral cluster |
| IV. Fixture Discipline | ✅ PASS | No fixture changes required |
| V. Kubernetes API First | ✅ PASS | Using openshift-python-wrapper for ODH installation |
| VI. Locality of Behavior | ✅ PASS | Pipeline in `.tekton/`, ITS CR in `konflux/` |
| VII. Security Awareness | ✅ PASS | EaaS handles credentials; no secrets in code |

## Project Structure

### Documentation (this feature)

```text
specs/konflux-integration/
├── spec.md              # Feature specification
├── plan.md              # This file
└── tasks.md             # Task breakdown (to be generated)
```

### Source Code (repository root)

```text
.tekton/                                    # NEW: Tekton pipeline for ITS
└── integration-test-pipeline.yaml          # Main integration test pipeline (Path A)

.github/workflows/                          # NEW: GitHub Actions for GPU tests
└── gpu-tests.yaml                          # GPU test workflow (Path B)

konflux/                                    # NEW: Konflux resources
├── integration-test-scenario-smoke.yaml    # ITS CR for smoke tests (non-GPU)
└── integration-test-scenario-sanity.yaml   # ITS CR for sanity tests (Phase 2)

scripts/                                    # NEW: Helper scripts for pipeline
├── install-odh.sh                          # ODH operator installation
├── parse-snapshot.py                       # Extract component images from SNAPSHOT
└── apply-snapshot-images.py                # Apply SNAPSHOT images to DSC

infra/                                      # NEW: Infrastructure definitions (Path B)
└── gpu-cluster/
    ├── README.md                           # GPU cluster setup instructions
    └── node-pool-config.yaml               # GPU node pool configuration

tests/
└── conftest.py                             # MODIFY: Add SNAPSHOT-aware fixtures (optional)

Dockerfile                                  # EXISTING: No changes needed
```

**Structure Decision**: Adding `.tekton/` for pipeline and `konflux/` for ITS CRs. Following Konflux conventions where pipeline is referenced via git resolver from ITS CR. Minimal test code changes.

## Research Findings

### Konflux ITS Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     KONFLUX INTEGRATION SERVICE                           │
│                                                                          │
│  [Component Build] → [Snapshot Created] → [ITS Triggered]                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    INTEGRATION TEST PIPELINE                              │
│                                                                          │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐        │
│  │ provision-eaas- │   │ provision-      │   │ get-cluster-    │        │
│  │ space           │ → │ cluster         │ → │ credentials     │        │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘        │
│           │                                           │                  │
│           ▼                                           ▼                  │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐        │
│  │ install-odh     │ → │ run-tests       │ → │ collect-results │        │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘        │
│                                                                          │
│  [finally]                                                               │
│  ┌─────────────────┐   ┌─────────────────┐                              │
│  │ collect-must-   │ → │ report-status   │                              │
│  │ gather          │   │                 │                              │
│  └─────────────────┘   └─────────────────┘                              │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### SNAPSHOT Parameter Structure

```json
{
  "application": "odh-application",
  "components": [
    {
      "name": "odh-dashboard",
      "containerImage": "quay.io/opendatahub/odh-dashboard@sha256:abc123..."
    },
    {
      "name": "model-controller",
      "containerImage": "quay.io/opendatahub/model-controller@sha256:def456..."
    }
  ],
  "artifacts": {}
}
```

### Konflux EaaS StepActions

From [konflux-ci/build-definitions](https://github.com/konflux-ci/build-definitions):

| StepAction | Purpose |
|------------|---------|
| `eaas-provision-space` | Create EaaS space for cluster provisioning |
| `eaas-get-supported-ephemeral-cluster-versions` | Get available OCP versions |
| `eaas-get-latest-openshift-version-by-prefix` | Select specific OCP version |
| `eaas-create-ephemeral-cluster-hypershift-aws` | Provision HyperShift cluster |
| `eaas-get-ephemeral-cluster-credentials` | Retrieve kubeconfig |

### IntegrationTestScenario CR Structure

```yaml
apiVersion: appstudio.redhat.com/v1beta2
kind: IntegrationTestScenario
metadata:
  name: odh-smoke-tests
  namespace: <konflux-namespace>
spec:
  application: <application-name>
  contexts:
    - description: ODH smoke tests on ephemeral cluster
      name: application
  resolverRef:
    resolver: git
    params:
      - name: url
        value: https://github.com/opendatahub-io/opendatahub-tests
      - name: revision
        value: main
      - name: pathInRepo
        value: .tekton/integration-test-pipeline.yaml
  params:
    - name: TEST_MARKERS
      value: smoke
```

## GPU Limitation & Hybrid Architecture

### Konflux EaaS GPU Limitation

**Critical Finding**: The Konflux EaaS `eaas-create-ephemeral-cluster-hypershift-aws` StepAction does **NOT** support GPU instance types.

**Supported Instance Types** (from [EaaS StepAction documentation](https://github.com/konflux-ci/build-definitions/tree/main/stepactions/eaas-create-ephemeral-cluster-hypershift-aws)):

```
Supported values: m5.large, m5.xlarge, m5.2xlarge, m6g.large, m6g.xlarge, m6g.2xlarge
```

**Not Available**: `g4dn.*` (NVIDIA T4), `g5.*` (NVIDIA A10G), `p3.*`, `p4d.*` or any GPU-enabled instances.

### Hybrid Architecture Design

To accommodate GPU workloads, we implement a **two-path architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           HYBRID TEST ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────┐    ┌─────────────────────────────────┐   │
│   │   PATH A: NON-GPU TESTS         │    │   PATH B: GPU TESTS             │   │
│   │   (Konflux ITS - Ephemeral)     │    │   (Dedicated Cluster)           │   │
│   ├─────────────────────────────────┤    ├─────────────────────────────────┤   │
│   │                                 │    │                                 │   │
│   │  Cluster: EaaS HyperShift      │    │  Cluster: Persistent OCP       │   │
│   │  Nodes: m5.xlarge / m6g.xlarge │    │  Nodes: g4dn.xlarge + g5.xlarge│   │
│   │  GPU: ❌ None                   │    │  GPU: ✅ NVIDIA T4 / A10G       │   │
│   │  Lifecycle: Ephemeral          │    │  Lifecycle: Always running     │   │
│   │  Trigger: Component build      │    │  Trigger: Nightly / Manual     │   │
│   │                                 │    │                                 │   │
│   │  Test Selection:               │    │  Test Selection:               │   │
│   │  -m "smoke and not gpu"        │    │  -m "gpu or model_server_gpu"  │   │
│   │  -m "sanity and not gpu"       │    │  -m "llmd_gpu"                 │   │
│   │                                 │    │                                 │   │
│   └─────────────────────────────────┘    └─────────────────────────────────┘   │
│                                                                                 │
│   Coordination:                                                                 │
│   • ITS (Path A) runs automatically on every component build                   │
│   • GPU tests (Path B) run nightly or after ITS passes                         │
│   • Both paths use same SNAPSHOT for component image validation                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Path A: Non-GPU Tests (ITS Pipeline)

| Aspect | Configuration |
|--------|---------------|
| **Pipeline** | `.tekton/integration-test-pipeline.yaml` |
| **ITS CR** | `konflux/integration-test-scenario-smoke.yaml` |
| **Cluster** | Ephemeral HyperShift via EaaS |
| **Instance Type** | `m5.xlarge` (4 vCPU, 16 GB RAM) |
| **Test Markers** | `-m "smoke and not gpu"` |
| **Trigger** | Automatic on component build |
| **Duration** | <45 minutes |

### Path B: GPU Tests (Dedicated Cluster)

| Aspect | Configuration |
|--------|---------------|
| **Pipeline** | `.github/workflows/gpu-tests.yaml` or separate Tekton pipeline |
| **Cluster** | Persistent OpenShift with GPU nodes |
| **Instance Type** | `g4dn.xlarge` (1x NVIDIA T4, 16GB VRAM) |
| **GPU Operator** | NVIDIA GPU Operator + Node Feature Discovery |
| **Test Markers** | `-m "gpu or model_server_gpu or llmd_gpu"` |
| **Trigger** | Scheduled (nightly) or manual after ITS passes |
| **Duration** | Variable (depends on test suite) |

### Dedicated GPU Cluster Specification

```yaml
# Infrastructure requirements for Path B dedicated GPU cluster
cluster:
  provider: AWS
  openshift_version: "4.16+"

node_pools:
  # Control plane (managed by OCP)
  control_plane:
    instance_type: m5.xlarge
    count: 3

  # Worker nodes for non-GPU workloads
  workers:
    instance_type: m5.2xlarge
    count: 3

  # GPU node pool for ML workloads
  gpu_workers:
    instance_type: g4dn.xlarge  # 1x NVIDIA T4, 16GB VRAM
    count: 2-4
    labels:
      nvidia.com/gpu.present: "true"
    taints:
      - key: nvidia.com/gpu
        value: "true"
        effect: NoSchedule

required_operators:
  - name: Node Feature Discovery
    namespace: openshift-nfd
  - name: NVIDIA GPU Operator
    namespace: nvidia-gpu-operator
  - name: Open Data Hub Operator
    namespace: openshift-operators

estimated_cost:
  g4dn.xlarge: $0.526/hour per node
  monthly_2_nodes: ~$760/month (24x7)
```

### Test Marker Strategy

Update `pytest.ini` markers and ensure tests are properly tagged:

```python
# tests/model_serving/gpu/test_vllm.py
@pytest.mark.gpu           # Excludes from ITS
@pytest.mark.model_server_gpu
@pytest.mark.tier1
def test_vllm_llama_inference():
    """Test vLLM inference with Llama model on GPU."""
    ...

# tests/model_serving/cpu/test_sklearn.py
@pytest.mark.smoke         # Included in ITS
def test_sklearn_model_serving():
    """Test sklearn model serving on CPU."""
    ...
```

### Pipeline Test Selection

**ITS Pipeline** (Path A):
```bash
uv run pytest -m "smoke and not gpu" tests/
```

**GPU Pipeline** (Path B):
```bash
uv run pytest -m "gpu or model_server_gpu or llmd_gpu" tests/
```

## Implementation Phases

### Phase 0: Pipeline Skeleton

**Goal**: Create basic pipeline structure that provisions cluster and runs a simple test

**Tasks**:
1. Create `.tekton/integration-test-pipeline.yaml` with SNAPSHOT parameter
2. Implement cluster provisioning using EaaS StepActions (copy from pipeline-samples)
3. Add simple test task that validates cluster access
4. Create `konflux/integration-test-scenario-smoke.yaml` ITS CR
5. Test manually by applying resources to Konflux namespace

**Deliverables**:
- `.tekton/integration-test-pipeline.yaml` - Basic pipeline with cluster provisioning
- `konflux/integration-test-scenario-smoke.yaml` - ITS CR for smoke tests

### Phase 1: ODH Installation

**Goal**: Install ODH operator and create DSC with SNAPSHOT images

**Tasks**:
1. Create `scripts/parse-snapshot.py` to extract component images
2. Create `scripts/install-odh.sh` for operator installation
3. Add install-odh task to pipeline
4. Implement DSC/DSCI creation with SNAPSHOT images
5. Add readiness wait logic

**Deliverables**:
- `scripts/parse-snapshot.py` - SNAPSHOT parsing utility
- `scripts/install-odh.sh` - ODH installation script
- Updated pipeline with install-odh task

### Phase 2: Test Execution (Path A - Non-GPU)

**Goal**: Run pytest smoke tests (excluding GPU) and collect results

**Tasks**:
1. Add run-tests task using opendatahub-tests container image
2. Configure pytest with `-m "smoke and not gpu"` marker (exclude GPU tests)
3. Generate JUnit XML report
4. Upload test artifacts to Konflux storage
5. Set pipeline result based on test outcome

**Deliverables**:
- Updated pipeline with run-tests task
- JUnit XML artifact upload
- Pipeline results reporting

### Phase 3: Failure Handling & Artifacts

**Goal**: Collect must-gather on failure and ensure proper cleanup

**Tasks**:
1. Add finally block with must-gather collection
2. Implement conditional must-gather (only on failure)
3. Archive and upload must-gather to artifact storage
4. Ensure cluster cleanup happens after artifact collection

**Deliverables**:
- Updated pipeline with finally block
- Must-gather collection and upload
- Proper cleanup sequencing

### Phase 4: Documentation & Validation

**Goal**: Production-ready with documentation

**Tasks**:
1. Create `docs/KONFLUX_ITS.md` with usage instructions
2. Add troubleshooting guide
3. Test ITS with real component builds
4. Create sanity test ITS variant

**Deliverables**:
- `docs/KONFLUX_ITS.md` - User documentation
- `konflux/integration-test-scenario-sanity.yaml` - Sanity ITS CR
- Validated end-to-end flow

### Phase 5: GPU Test Integration (Path B - Dedicated Cluster)

**Goal**: Enable GPU tests on dedicated persistent cluster

**Tasks**:
1. Document dedicated GPU cluster requirements in `infra/gpu-cluster/README.md`
2. Create GPU node pool configuration template
3. Create `.github/workflows/gpu-tests.yaml` for GPU test execution
4. Implement SNAPSHOT parameter passing to GPU pipeline
5. Configure nightly trigger and manual dispatch
6. Set up result reporting back to Konflux (optional webhook/API)

**Deliverables**:
- `infra/gpu-cluster/README.md` - GPU cluster setup guide
- `infra/gpu-cluster/node-pool-config.yaml` - GPU node configuration
- `.github/workflows/gpu-tests.yaml` - GPU test GitHub Action
- Documentation for hybrid architecture operation

**Prerequisites**:
- Dedicated OpenShift cluster with GPU nodes provisioned
- NVIDIA GPU Operator installed
- Node Feature Discovery installed
- ServiceAccount credentials for test execution

**GPU Cluster Setup Checklist**:
- [ ] AWS account with GPU instance quota (g4dn.xlarge or g5.xlarge)
- [ ] OpenShift 4.14+ cluster deployed
- [ ] GPU node pool with 2-4 g4dn.xlarge nodes
- [ ] Node Feature Discovery Operator installed
- [ ] NVIDIA GPU Operator installed and configured
- [ ] ODH/RHOAI operator installed
- [ ] ServiceAccount with appropriate RBAC for tests
- [ ] Kubeconfig secret accessible to GitHub Actions

## Technical Design

### Integration Test Pipeline

```yaml
# .tekton/integration-test-pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: odh-integration-tests
spec:
  description: |
    Integration test pipeline for ODH components. Provisions an ephemeral
    HyperShift cluster, installs ODH with SNAPSHOT component images, and
    runs smoke tests.
  params:
    - name: SNAPSHOT
      type: string
      description: Snapshot containing built component images (JSON)
    - name: TEST_MARKERS
      type: string
      default: smoke
      description: pytest markers for test selection
    - name: OCP_VERSION_PREFIX
      type: string
      default: "4.16"
      description: OpenShift version prefix for ephemeral cluster

  tasks:
    # Step 1: Provision EaaS space
    - name: provision-eaas-space
      taskRef:
        resolver: git
        params:
          - name: url
            value: https://github.com/konflux-ci/build-definitions.git
          - name: revision
            value: main
          - name: pathInRepo
            value: task/eaas-provision-space/0.1/eaas-provision-space.yaml
      params:
        - name: ownerName
          value: $(context.pipelineRun.name)
        - name: ownerUid
          value: $(context.pipelineRun.uid)

    # Step 2: Provision ephemeral cluster
    - name: provision-cluster
      runAfter:
        - provision-eaas-space
      taskSpec:
        results:
          - name: clusterName
            value: "$(steps.create-cluster.results.clusterName)"
        volumes:
          - name: credentials
            emptyDir: {}
        steps:
          - name: get-supported-versions
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-get-supported-ephemeral-cluster-versions/0.1/eaas-get-supported-ephemeral-cluster-versions.yaml
            params:
              - name: eaasSpaceSecretRef
                value: $(tasks.provision-eaas-space.results.secretRef)
          - name: pick-version
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-get-latest-openshift-version-by-prefix/0.1/eaas-get-latest-openshift-version-by-prefix.yaml
            params:
              - name: prefix
                value: "$(params.OCP_VERSION_PREFIX)."
          - name: create-cluster
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-create-ephemeral-cluster-hypershift-aws/0.1/eaas-create-ephemeral-cluster-hypershift-aws.yaml
            params:
              - name: eaasSpaceSecretRef
                value: $(tasks.provision-eaas-space.results.secretRef)
              - name: version
                value: "$(steps.pick-version.results.version)"

    # Step 3: Install ODH with SNAPSHOT images
    - name: install-odh
      runAfter:
        - provision-cluster
      params:
        - name: SNAPSHOT
          value: $(params.SNAPSHOT)
      taskSpec:
        params:
          - name: SNAPSHOT
            type: string
        volumes:
          - name: credentials
            emptyDir: {}
        steps:
          - name: get-kubeconfig
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-get-ephemeral-cluster-credentials/0.1/eaas-get-ephemeral-cluster-credentials.yaml
            params:
              - name: eaasSpaceSecretRef
                value: $(tasks.provision-eaas-space.results.secretRef)
              - name: clusterName
                value: $(tasks.provision-cluster.results.clusterName)
              - name: credentials
                value: credentials
          - name: install-operator
            image: quay.io/openshift/origin-cli:latest
            env:
              - name: KUBECONFIG
                value: /credentials/$(steps.get-kubeconfig.results.kubeconfig)
              - name: SNAPSHOT
                value: $(params.SNAPSHOT)
            volumeMounts:
              - name: credentials
                mountPath: /credentials
            script: |
              #!/bin/bash
              set -euxo pipefail

              # Install ODH operator from community-operators
              cat <<EOF | oc apply -f -
              apiVersion: operators.coreos.com/v1alpha1
              kind: Subscription
              metadata:
                name: opendatahub-operator
                namespace: openshift-operators
              spec:
                channel: fast
                name: opendatahub-operator
                source: community-operators
                sourceNamespace: openshift-marketplace
              EOF

              # Wait for operator to be ready
              echo "Waiting for ODH operator..."
              oc wait --for=condition=Available \
                deployment/opendatahub-operator-controller-manager \
                -n openshift-operators \
                --timeout=300s

              # Parse SNAPSHOT and create DSC
              # TODO: Use scripts/parse-snapshot.py for proper image mapping
              cat <<EOF | oc apply -f -
              apiVersion: datasciencecluster.opendatahub.io/v1
              kind: DataScienceCluster
              metadata:
                name: default-dsc
              spec:
                components:
                  dashboard:
                    managementState: Managed
                  modelmeshserving:
                    managementState: Managed
                  kserve:
                    managementState: Managed
              EOF

              # Wait for DSC to be ready
              echo "Waiting for DSC..."
              oc wait --for=condition=Available \
                datasciencecluster/default-dsc \
                --timeout=600s

    # Step 4: Run integration tests
    - name: run-tests
      runAfter:
        - install-odh
      params:
        - name: TEST_MARKERS
          value: $(params.TEST_MARKERS)
        - name: SNAPSHOT
          value: $(params.SNAPSHOT)
      taskSpec:
        params:
          - name: TEST_MARKERS
            type: string
          - name: SNAPSHOT
            type: string
        results:
          - name: test-result
            description: Test execution result (PASSED/FAILED)
        volumes:
          - name: credentials
            emptyDir: {}
          - name: artifacts
            emptyDir: {}
        steps:
          - name: get-kubeconfig
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-get-ephemeral-cluster-credentials/0.1/eaas-get-ephemeral-cluster-credentials.yaml
            params:
              - name: eaasSpaceSecretRef
                value: $(tasks.provision-eaas-space.results.secretRef)
              - name: clusterName
                value: $(tasks.provision-cluster.results.clusterName)
              - name: credentials
                value: credentials
          - name: run-pytest
            image: quay.io/opendatahub/opendatahub-tests:latest
            env:
              - name: KUBECONFIG
                value: /credentials/$(steps.get-kubeconfig.results.kubeconfig)
              - name: SNAPSHOT
                value: $(params.SNAPSHOT)
            volumeMounts:
              - name: credentials
                mountPath: /credentials
              - name: artifacts
                mountPath: /artifacts
            script: |
              #!/bin/bash
              set -x

              # Run pytest with markers
              uv run pytest \
                -m "$(params.TEST_MARKERS)" \
                --junitxml=/artifacts/junit.xml \
                --tc=distribution:upstream \
                tests/ || TEST_EXIT_CODE=$?

              # Save exit code for result
              if [ "${TEST_EXIT_CODE:-0}" -eq 0 ]; then
                echo "PASSED" > $(results.test-result.path)
              else
                echo "FAILED" > $(results.test-result.path)
                exit $TEST_EXIT_CODE
              fi

  finally:
    - name: collect-must-gather
      when:
        - input: $(tasks.run-tests.results.test-result)
          operator: in
          values: ["FAILED"]
      taskSpec:
        volumes:
          - name: credentials
            emptyDir: {}
          - name: artifacts
            emptyDir: {}
        steps:
          - name: get-kubeconfig
            ref:
              resolver: git
              params:
                - name: url
                  value: https://github.com/konflux-ci/build-definitions.git
                - name: revision
                  value: main
                - name: pathInRepo
                  value: stepactions/eaas-get-ephemeral-cluster-credentials/0.1/eaas-get-ephemeral-cluster-credentials.yaml
            params:
              - name: eaasSpaceSecretRef
                value: $(tasks.provision-eaas-space.results.secretRef)
              - name: clusterName
                value: $(tasks.provision-cluster.results.clusterName)
              - name: credentials
                value: credentials
          - name: run-must-gather
            image: quay.io/openshift/origin-cli:latest
            env:
              - name: KUBECONFIG
                value: /credentials/$(steps.get-kubeconfig.results.kubeconfig)
            volumeMounts:
              - name: credentials
                mountPath: /credentials
              - name: artifacts
                mountPath: /artifacts
            script: |
              #!/bin/bash
              set -x

              # Run must-gather
              oc adm must-gather \
                --dest-dir=/artifacts/must-gather \
                --timeout=10m || true

              # Compress artifacts
              tar -czf /artifacts/must-gather.tar.gz \
                -C /artifacts must-gather || true

              echo "Must-gather collected"
```

### IntegrationTestScenario CR

```yaml
# konflux/integration-test-scenario-smoke.yaml
apiVersion: appstudio.redhat.com/v1beta2
kind: IntegrationTestScenario
metadata:
  name: odh-smoke-tests
  namespace: <konflux-namespace>  # Replace with actual namespace
spec:
  application: <application-name>  # Replace with ODH application name
  contexts:
    - description: ODH smoke tests on ephemeral HyperShift cluster
      name: application
  resolverRef:
    resolver: git
    params:
      - name: url
        value: https://github.com/opendatahub-io/opendatahub-tests
      - name: revision
        value: main
      - name: pathInRepo
        value: .tekton/integration-test-pipeline.yaml
  params:
    - name: TEST_MARKERS
      value: smoke
    - name: OCP_VERSION_PREFIX
      value: "4.16"
```

### SNAPSHOT Parsing Script

```python
#!/usr/bin/env python3
# scripts/parse-snapshot.py
"""Parse Konflux SNAPSHOT and extract component images."""

import json
import sys
from typing import Any


def parse_snapshot(snapshot_json: str) -> dict[str, str]:
    """
    Parse SNAPSHOT JSON and return component name to image mapping.

    Args:
        snapshot_json: JSON string from Konflux SNAPSHOT parameter

    Returns:
        Dictionary mapping component names to container images
    """
    snapshot = json.loads(snapshot_json)
    components = {}

    for component in snapshot.get("components", []):
        name = component.get("name", "")
        image = component.get("containerImage", "")
        if name and image:
            components[name] = image

    return components


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: parse-snapshot.py '<SNAPSHOT_JSON>'", file=sys.stderr)
        sys.exit(1)

    snapshot_json = sys.argv[1]
    components = parse_snapshot(snapshot_json)

    # Output as KEY=VALUE for shell consumption
    for name, image in components.items():
        # Normalize component name to env var format
        env_name = name.upper().replace("-", "_")
        print(f"{env_name}_IMAGE={image}")


if __name__ == "__main__":
    main()
```

## Complexity Tracking

| Aspect | Complexity | Justification |
|--------|------------|---------------|
| Ephemeral cluster provisioning | Low | Using Konflux EaaS StepActions directly |
| ODH installation | Medium | Standard operator installation; DSC creation |
| SNAPSHOT parsing | Low | Simple JSON parsing |
| Test execution | Low | Existing container image and pytest setup |
| Must-gather collection | Low | Standard oc adm must-gather |
| ITS configuration | Low | Standard Konflux CR |

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Cluster provisioning timeout | 25 min timeout; fail fast with clear error |
| ODH installation failure | Collect logs before failing; must-gather in finally |
| EaaS quota exhaustion | Document quota limits; queue with timeout |
| Test container image unavailable | Build image in separate pipeline; use stable tag |
| SNAPSHOT missing components | Validate SNAPSHOT structure early; fail with clear error |

## Dependencies

### External Dependencies
- Konflux platform access with EaaS enabled
- Konflux EaaS quota for HyperShift clusters
- Access to OperatorHub (community-operators)
- opendatahub-tests container image in quay.io

### Internal Dependencies
- Existing Dockerfile (no changes needed)
- Existing pytest infrastructure (minimal changes)
- Existing must-gather implementation

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| ITS trigger success rate | 100% | Konflux pipeline triggers |
| Cluster provisioning success | 95% | EaaS cluster creation |
| ODH installation success | 98% | Operator and DSC ready |
| Total pipeline duration | <45 min | End-to-end time |
| Test execution time | <15 min | pytest duration only |
| Must-gather availability | 100% on failure | Artifact presence check |

## Open Questions

1. **Application name**: What is the Konflux application name for ODH components?
   - **Action**: Confirm with Konflux team

2. **Namespace**: Which Konflux namespace should ITS be deployed to?
   - **Action**: Confirm with Konflux team

3. **Image tag strategy**: Use `latest` or specific version for test container?
   - **Proposed**: Use `latest` initially; consider SHA pinning later

4. **OCP version**: Which OpenShift version(s) to test against?
   - **Proposed**: Default to 4.16; parameterize for flexibility

5. **SNAPSHOT image mapping**: How to map SNAPSHOT components to DSC fields?
   - **Proposed**: Start with dashboard; expand mapping as needed

6. **GPU cluster provisioning**: Who provisions and maintains the dedicated GPU cluster?
   - **Action**: Confirm infrastructure ownership (QE team, Platform team, or shared)
   - **Cost consideration**: ~$760/month for 2x g4dn.xlarge nodes running 24x7

7. **GPU cluster access**: How will GitHub Actions authenticate to the dedicated GPU cluster?
   - **Proposed**: ServiceAccount token stored as GitHub secret
   - **Alternative**: Use Konflux secrets if GPU pipeline runs as separate ITS

8. **GPU test frequency**: How often should GPU tests run?
   - **Proposed**: Nightly (to control costs) with manual trigger option
   - **Alternative**: On-demand after non-GPU ITS passes

9. **Konflux GPU support roadmap**: Will Konflux EaaS add GPU instance support in the future?
   - **Action**: Check with Konflux team; may enable unified architecture later
   - **Fallback**: Hybrid architecture remains viable long-term solution

## References

### Konflux & ITS
- [Konflux Integration Service](https://github.com/konflux-ci/integration-service)
- [Konflux Pipeline Samples](https://github.com/konflux-ci/pipeline-samples)
- [Konflux Build Definitions](https://github.com/konflux-ci/build-definitions)
- [Ephemeral Clusters in Konflux](https://developers.redhat.com/articles/2024/10/28/ephemeral-openshift-clusters-konflux-ci-using-cluster-service-operator)
- [IntegrationTestScenario CRD](https://github.com/konflux-ci/integration-service/blob/main/config/crd/bases/appstudio.redhat.com_integrationtestscenarios.yaml)
- [EaaS StepAction - Supported Instance Types](https://github.com/konflux-ci/build-definitions/tree/main/stepactions/eaas-create-ephemeral-cluster-hypershift-aws)

### GPU Infrastructure
- [AWS EC2 G4 Instances (NVIDIA T4)](https://aws.amazon.com/ec2/instance-types/g4/)
- [AWS EC2 G5 Instances (NVIDIA A10G)](https://aws.amazon.com/ec2/instance-types/g5/)
- [NVIDIA GPU Operator Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html)
- [OpenShift Node Feature Discovery](https://docs.openshift.com/container-platform/latest/hardware_enablement/psap-node-feature-discovery-operator.html)
