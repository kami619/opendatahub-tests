# Implementation Plan: Konflux IT Integration

**Branch**: `konflux-integration` | **Date**: 2026-01-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/konflux-integration/spec.md`

## Summary

Enable Konflux (Tekton-based) CI/CD pipelines to execute opendatahub-tests integration tests against RHOAI deployments. This replaces the current static-only GitHub Actions with full integration test execution, supporting smoke tests on PR, tier1 tests on merge, and parallel execution with proper isolation.

## Technical Context

**Language/Version**: Python 3.13 (existing), YAML (Tekton pipelines)
**Primary Dependencies**: pytest, pytest-xdist, openshift-python-wrapper, Tekton Pipelines v1
**Storage**: S3-compatible storage for artifacts (existing), Konflux artifact storage
**Testing**: pytest with existing test infrastructure
**Target Platform**: OpenShift 4.x with Konflux/Tekton Pipelines
**Project Type**: CI/CD pipeline integration (infrastructure-as-code)
**Performance Goals**: Smoke tests <30min, Tier1 <2h, 3x speedup with parallelism
**Constraints**: ServiceAccount auth only (no user credentials), namespace isolation per worker
**Scale/Scope**: ~295 test files, ~113 test modules, 7 components

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First | ✅ PASS | Using standard Tekton patterns, minimal custom logic |
| II. Code Consistency | ✅ PASS | Following existing pytest/conftest patterns |
| III. Test Independence | ✅ PASS | Namespace isolation ensures test independence |
| IV. Fixture Discipline | ✅ PASS | Existing fixtures work; adding CI-specific fixtures |
| V. Kubernetes API First | ✅ PASS | Using openshift-python-wrapper for all K8s interactions |
| VI. Locality of Behavior | ✅ PASS | Pipeline configs in `.tekton/`, test code unchanged |
| VII. Security Awareness | ✅ PASS | ServiceAccount auth, no secrets in code |

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
.tekton/                           # NEW: Tekton pipeline definitions
├── pipeline.yaml                  # Main pipeline definition
├── tasks/
│   ├── build-test-image.yaml     # Build container from Dockerfile
│   ├── run-pytest.yaml           # Execute pytest with markers
│   ├── collect-artifacts.yaml    # Collect must-gather and reports
│   └── cleanup.yaml              # Namespace cleanup
├── triggers/
│   ├── pr-trigger.yaml           # PipelineRun on PR
│   └── merge-trigger.yaml        # PipelineRun on merge
└── config/
    ├── test-config.yaml          # ConfigMap template
    └── rbac-template.yaml        # ServiceAccount RBAC

configs/                           # NEW: Environment configurations
├── konflux-smoke.yaml            # Smoke test configuration
├── konflux-tier1.yaml            # Tier1 test configuration
└── konflux-full.yaml             # Full test suite configuration

tests/
├── conftest.py                   # MODIFY: Add CI detection fixtures
└── fixtures/
    └── ci.py                     # NEW: CI-specific fixtures

utilities/
├── ci_utils.py                   # NEW: CI helper functions
└── constants.py                  # MODIFY: Add CI-related constants

Dockerfile                         # MODIFY: Optimize for CI builds
```

**Structure Decision**: Adding `.tekton/` directory for pipeline definitions following Konflux conventions. Minimal changes to existing test code; CI-specific logic isolated in dedicated modules.

## Research Findings

### Current State Analysis (from Archie's Assessment)

**Existing CI/CD:**
- GitHub Actions: Static checks only (tox, pre-commit)
- Dockerfile: Present but not used in CI
- pytest-xdist: Configured but not used in CI
- Must-gather: Implemented but manual trigger

**Gaps Identified:**
- No Tekton pipeline definitions
- No integration test execution in CI
- No ServiceAccount-based authentication
- No test sharding strategy
- No artifact collection automation

### Konflux Integration Requirements

**Pipeline Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    KONFLUX PIPELINE                             │
│                                                                 │
│  [PR/Merge Event] → [Build Test Image] → [Configure Cluster]   │
│                                                                 │
│      ↓                                                          │
│  [Run Integration Tests] → [Collect Results] → [Report Status] │
│                                                                 │
│      ↓ (on failure)                                             │
│  [Collect Must-Gather] → [Archive Artifacts] → [Cleanup]       │
└─────────────────────────────────────────────────────────────────┘
```

**Authentication Model:**
- ServiceAccount with RBAC for test namespaces
- Token mounted via Kubernetes secrets
- No user credentials in pipeline

**Parallelization Strategy:**
- pytest-xdist with `--dist loadscope` for class-based distribution
- Each worker gets unique namespace via `--basetemp` and fixture
- GPU tests excluded from parallel execution (`-m "parallel and not gpu"`)

## Implementation Phases

### Phase 0: Foundation (Week 1)

**Goal**: Basic pipeline structure that can run a single test

1. Create `.tekton/` directory structure
2. Define base pipeline with build and test tasks
3. Implement ServiceAccount authentication
4. Validate pipeline runs manually

**Deliverables**:
- `.tekton/pipeline.yaml` - Basic pipeline skeleton
- `.tekton/tasks/build-test-image.yaml` - Container build task
- `.tekton/tasks/run-pytest.yaml` - Basic test execution
- `.tekton/config/rbac-template.yaml` - ServiceAccount RBAC

### Phase 1: Smoke Test Pipeline (Week 2)

**Goal**: PR-triggered smoke tests with basic reporting

1. Implement PR trigger configuration
2. Add marker-based test selection
3. Implement JUnit XML report generation
4. Configure GitHub status reporting

**Deliverables**:
- `.tekton/triggers/pr-trigger.yaml`
- ConfigMap for smoke test parameters
- JUnit report artifact upload
- PR status integration

### Phase 2: Parallel Execution (Week 3)

**Goal**: Enable parallel test execution with isolation

1. Implement namespace-per-worker isolation
2. Add pytest-xdist configuration to pipeline
3. Create CI-specific fixtures for namespace management
4. Implement result aggregation

**Deliverables**:
- `tests/fixtures/ci.py` - CI fixtures
- Modified `run-pytest.yaml` with xdist support
- Namespace cleanup task
- Aggregated test reports

### Phase 3: Artifact Collection (Week 4)

**Goal**: Automated must-gather and artifact management

1. Implement failure detection in pipeline
2. Add must-gather collection task
3. Configure artifact upload to Konflux storage
4. Add merge-triggered tier1 pipeline

**Deliverables**:
- `.tekton/tasks/collect-artifacts.yaml`
- `.tekton/triggers/merge-trigger.yaml`
- Must-gather archive upload
- Tier1 configuration

### Phase 4: Configuration & Polish (Week 5)

**Goal**: Production-ready configuration management

1. Create environment-specific configurations
2. Implement configuration validation
3. Add documentation
4. Performance optimization

**Deliverables**:
- `configs/` directory with profiles
- Configuration schema validation
- Updated `docs/KONFLUX_CI.md`
- Optimized Dockerfile

## Technical Design

### Pipeline Definition

```yaml
# .tekton/pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: opendatahub-tests
spec:
  params:
    - name: test-markers
      type: string
      default: "smoke"
    - name: parallel-workers
      type: string
      default: "4"
    - name: cluster-name
      type: string
    - name: distribution
      type: string
      default: "downstream"

  workspaces:
    - name: source
    - name: artifacts

  tasks:
    - name: build-test-image
      taskRef:
        name: build-test-image
      workspaces:
        - name: source
          workspace: source

    - name: run-tests
      taskRef:
        name: run-pytest
      runAfter:
        - build-test-image
      params:
        - name: markers
          value: $(params.test-markers)
        - name: workers
          value: $(params.parallel-workers)
      workspaces:
        - name: source
          workspace: source
        - name: artifacts
          workspace: artifacts

    - name: collect-artifacts
      taskRef:
        name: collect-artifacts
      runAfter:
        - run-tests
      when:
        - input: $(tasks.run-tests.results.status)
          operator: in
          values: ["Failed", "Succeeded"]
      workspaces:
        - name: artifacts
          workspace: artifacts

  finally:
    - name: cleanup
      taskRef:
        name: cleanup
```

### Test Execution Task

```yaml
# .tekton/tasks/run-pytest.yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: run-pytest
spec:
  params:
    - name: markers
      type: string
    - name: workers
      type: string
      default: "1"

  workspaces:
    - name: source
    - name: artifacts

  steps:
    - name: run-tests
      image: $(params.test-image)
      env:
        - name: KUBECONFIG
          value: /var/run/secrets/kubernetes.io/serviceaccount/kubeconfig
      script: |
        #!/bin/bash
        set -e

        cd $(workspaces.source.path)

        # Configure pytest for CI
        export CI=true
        export PYTEST_XDIST_WORKERS=$(params.workers)

        # Run tests with markers
        uv run pytest \
          -m "$(params.markers)" \
          -n $(params.workers) \
          --dist loadscope \
          --junitxml=$(workspaces.artifacts.path)/junit.xml \
          --collect-must-gather \
          --tc=distribution:$(params.distribution) \
          2>&1 | tee $(workspaces.artifacts.path)/pytest.log

        # Capture exit code
        echo $? > $(workspaces.artifacts.path)/exit_code

  results:
    - name: status
      description: Test execution status
```

### CI Fixtures

```python
# tests/fixtures/ci.py
"""CI-specific fixtures for Konflux pipeline execution."""

import os
import pytest
from typing import Generator

from ocp_resources.namespace import Namespace
from kubernetes.dynamic import DynamicClient


def is_ci_environment() -> bool:
    """Detect if running in CI environment."""
    return os.environ.get("CI", "").lower() == "true"


@pytest.fixture(scope="session")
def ci_worker_id() -> str:
    """Get pytest-xdist worker ID for namespace isolation."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


@pytest.fixture(scope="session")
def ci_isolated_namespace(
    admin_client: DynamicClient,
    ci_worker_id: str,
) -> Generator[Namespace, None, None]:
    """
    Create isolated namespace for CI worker.

    Each pytest-xdist worker gets a unique namespace to prevent
    resource conflicts during parallel execution.
    """
    if not is_ci_environment():
        yield None
        return

    namespace_name = f"ci-test-{ci_worker_id}-{os.getpid()}"

    with Namespace(
        client=admin_client,
        name=namespace_name,
        labels={"opendatahub-tests/ci": "true"},
    ) as ns:
        yield ns
```

### Configuration Schema

```yaml
# configs/konflux-smoke.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: opendatahub-tests-smoke
data:
  markers: "smoke"
  parallel_workers: "4"
  timeout_minutes: "30"
  distribution: "downstream"
  collect_must_gather: "true"

  # Resource limits per namespace
  cpu_limit: "4"
  memory_limit: "8Gi"

  # Test selection
  exclude_markers: "gpu,slow"
```

## Complexity Tracking

| Aspect | Complexity | Justification |
|--------|------------|---------------|
| Parallel execution | Medium | Required for practical CI runtime; using standard pytest-xdist |
| Namespace isolation | Low | Simple fixture; prevents resource conflicts |
| ServiceAccount auth | Low | Standard Kubernetes pattern; no custom code |
| Must-gather collection | Low | Existing implementation; just automation |
| Multi-configuration | Low | ConfigMap-based; no complex logic |

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Pipeline flakiness | Implement retry for infrastructure failures; clear timeout handling |
| Resource exhaustion | Namespace quotas; sequential GPU tests; cleanup task in finally |
| Auth token expiration | Short-lived tokens; refresh mechanism in long-running tests |
| Must-gather size | Compression; time-bounded collection; selective namespace gathering |

## Dependencies

### External Dependencies
- Konflux platform access
- Target RHOAI cluster(s) with ServiceAccount permissions
- S3-compatible artifact storage

### Internal Dependencies
- Existing Dockerfile (optimize, don't replace)
- Existing pytest infrastructure (extend, don't modify)
- Existing must-gather implementation (automate trigger)

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Smoke test duration | <30 min | Pipeline run time |
| Tier1 test duration | <2 hours | Pipeline run time |
| Parallelization speedup | 3x minimum | Compare sequential vs parallel |
| Infrastructure failure rate | <5% | Pipeline failures not caused by test failures |
| Artifact availability | 100% on failure | Check artifact presence for failed runs |

## Open Questions

1. **Cluster provisioning**: Will tests use pre-existing clusters or need ephemeral provisioning?
   - **Current assumption**: Pre-existing clusters; ephemeral provisioning out of scope for Phase 1

2. **GPU test handling**: How to handle GPU tests that can't run in parallel?
   - **Proposed**: Separate pipeline or sequential phase after parallel tests

3. **Cost optimization**: Any constraints on cluster usage time?
   - **Proposed**: Implement cleanup with aggressive timeout; monitor usage

4. **Notification**: Where should pipeline results be reported beyond PR checks?
   - **Proposed**: PR checks for MVP; Slack/email integration as follow-up
