# Feature Specification: Konflux Integration Test Scenario for RHOAI

**Feature Branch**: `konflux-integration`
**Created**: 2026-01-08
**Updated**: 2026-01-12
**Status**: Draft
**Input**: Run opendatahub-tests as an IntegrationTestScenario (ITS) in existing Konflux build pipelines

## Clarifications

### Session 2026-01-12

- Q: What is the integration model? → A: IntegrationTestScenario (ITS) - Tests run as part of existing Konflux component build pipelines, not as a standalone pipeline
- Q: How are tests triggered? → A: Automatically by Konflux Integration Service when a component build completes and a Snapshot is created
- Q: What cluster model for test execution? → A: Ephemeral clusters provisioned via Konflux EaaS (Environment as a Service) using HyperShift
- Q: How is the built component image used? → A: SNAPSHOT parameter contains built component images; tests deploy and validate these images
- Q: Which distributions are supported? → A: ODH (upstream) primary; RHOAI (downstream) secondary

### Session 2026-01-08 (Previous - Superseded)

- Previous clarifications about dedicated CI cluster model are superseded by ephemeral cluster approach

## Overview

This feature enables opendatahub-tests to run as an **IntegrationTestScenario (ITS)** within existing Konflux component build pipelines. When a component (e.g., ODH Dashboard, Model Controller) is built in Konflux, the Integration Service automatically creates a Snapshot and triggers the ITS pipeline to validate the newly built component.

**Integration Model**: IntegrationTestScenario CR references a Tekton Pipeline in this repository. Konflux Integration Service invokes this pipeline after component builds complete.

**Cluster Model**: Ephemeral HyperShift clusters provisioned on-demand via Konflux EaaS. Clusters are created at test start and destroyed after completion (10-20 min provisioning time).

**SNAPSHOT Parameter**: Konflux automatically provides a SNAPSHOT JSON parameter containing references to all built component images in the application. The test pipeline uses this to deploy and validate the correct image versions.

## User Scenarios & Testing

### User Story 1 - Component Validation via ITS (Priority: P1)

As a component developer, I want my component build to automatically trigger integration tests so that I know if my changes break functionality before the snapshot is promoted.

**Why this priority**: This is the core integration point with Konflux. Without this, there is no automated integration testing in the build pipeline.

**Independent Test**: Can be fully tested by triggering a component build and verifying the ITS pipeline runs with the correct SNAPSHOT.

**Acceptance Scenarios**:

1. **Given** a component build completes in Konflux, **When** the Integration Service creates a Snapshot, **Then** the opendatahub-tests ITS pipeline is triggered with the SNAPSHOT parameter.

2. **Given** the ITS pipeline receives a SNAPSHOT, **When** tests execute, **Then** the component image from the SNAPSHOT is deployed and validated.

3. **Given** the ITS pipeline completes, **When** all tests pass, **Then** the Snapshot is marked as passed and eligible for promotion.

4. **Given** the ITS pipeline fails, **When** tests report failures, **Then** the Snapshot is marked as failed and not promoted.

---

### User Story 2 - Ephemeral Cluster Provisioning (Priority: P1)

As a test engineer, I want tests to run on ephemeral OpenShift clusters so that each test run has a clean environment and I don't need to manage shared CI clusters.

**Why this priority**: Ephemeral clusters eliminate environment drift and resource conflicts. This is the Konflux-native approach.

**Independent Test**: Can be tested by triggering the ITS and verifying a HyperShift cluster is provisioned and credentials are available.

**Acceptance Scenarios**:

1. **Given** the ITS pipeline starts, **When** the provision-cluster task runs, **Then** an ephemeral HyperShift cluster is created via Konflux EaaS.

2. **Given** a cluster is provisioned, **When** credentials are retrieved, **Then** kubeconfig is available for test execution.

3. **Given** the ITS pipeline completes (pass or fail), **When** cleanup runs, **Then** the ephemeral cluster is destroyed.

4. **Given** cluster provisioning fails, **When** the failure is detected, **Then** the pipeline fails fast with clear error message.

---

### User Story 3 - ODH/RHOAI Installation on Ephemeral Cluster (Priority: P1)

As a test engineer, I want ODH or RHOAI automatically installed on the ephemeral cluster so that tests can validate component functionality.

**Why this priority**: Tests require a working ODH/RHOAI installation. Without automated installation, the ephemeral cluster approach is not viable.

**Independent Test**: Can be tested by provisioning a cluster and verifying ODH operator and components are installed.

**Acceptance Scenarios**:

1. **Given** an ephemeral cluster is provisioned, **When** the install task runs, **Then** the ODH operator is installed from OperatorHub.

2. **Given** a SNAPSHOT with component images, **When** installation completes, **Then** the DSC/DSCI resources are created with component images from SNAPSHOT.

3. **Given** installation is in progress, **When** components become ready, **Then** the pipeline proceeds to test execution.

4. **Given** installation times out, **When** components are not ready within 15 minutes, **Then** the pipeline fails with installation error.

---

### User Story 4 - Smoke Test Execution (Priority: P2)

As a component developer, I want fast smoke tests to run on my component build so that I get quick feedback without waiting for the full test suite.

**Why this priority**: ITS pipelines should be fast (Konflux guidance: not suitable for long-running tests). Smoke tests provide quick validation.

**Independent Test**: Can be tested by running the ITS with smoke markers and verifying completion within 30 minutes.

**Acceptance Scenarios**:

1. **Given** the ITS pipeline is configured for smoke tests, **When** pytest executes, **Then** only tests with `-m smoke` marker run.

2. **Given** smoke tests are running, **When** a test fails, **Then** failure details are captured in JUnit XML and pipeline results.

3. **Given** smoke tests complete, **When** results are aggregated, **Then** pass/fail status is reported to Konflux Integration Service.

---

### User Story 5 - Must-Gather on Failure (Priority: P2)

As a test engineer diagnosing failures, I want must-gather artifacts collected when tests fail so that I can debug issues.

**Why this priority**: Ephemeral clusters are destroyed after tests. Artifacts must be collected before cleanup.

**Independent Test**: Can be tested by intentionally failing a test and verifying must-gather archive is uploaded.

**Acceptance Scenarios**:

1. **Given** a test fails during execution, **When** the failure is detected, **Then** must-gather is triggered before cluster cleanup.

2. **Given** must-gather completes, **When** artifacts are collected, **Then** they are archived and uploaded to Konflux artifact storage.

3. **Given** the pipeline runs in finally block, **When** must-gather and cleanup execute, **Then** cleanup waits for must-gather completion.

---

### User Story 6 - Configurable Test Context (Priority: P3)

As a QE engineer, I want different ITS configurations for different contexts so that I can run appropriate tests for PR validation vs. release gating.

**Why this priority**: Different contexts need different test coverage. Flexibility enables appropriate testing at each stage.

**Independent Test**: Can be tested by creating multiple IntegrationTestScenario CRs with different configurations.

**Acceptance Scenarios**:

1. **Given** an ITS is configured with `contexts: [application]`, **When** triggered, **Then** it runs for all component builds.

2. **Given** an ITS is configured with `contexts: [component]`, **When** triggered, **Then** it runs only for specific component builds.

3. **Given** an ITS has custom parameters, **When** triggered, **Then** parameters are passed to the pipeline.

---

### Edge Cases

- What happens when ephemeral cluster provisioning times out?
  - Pipeline fails fast after 25 minutes; no cluster cleanup needed
- What happens when ODH installation fails?
  - Collect logs, trigger must-gather, fail pipeline with installation error
- How does system handle SNAPSHOT with multiple components?
  - Install all components from SNAPSHOT; validate the primary component being tested
- What happens when Konflux EaaS quota is exhausted?
  - Pipeline queues until quota available; configurable timeout (default 30 min)
- What happens when the test container image is not available?
  - Pipeline fails at image pull stage with clear error
- How does system handle tests that require GPU?
  - GPU tests are excluded from ITS (ephemeral clusters may not have GPU); run separately on dedicated cluster

## Requirements

### Functional Requirements

#### IntegrationTestScenario Configuration

- **FR-001**: System MUST define an IntegrationTestScenario CR that references the test pipeline
- **FR-002**: System MUST accept SNAPSHOT parameter from Konflux Integration Service
- **FR-003**: System MUST support multiple ITS configurations (smoke, sanity) via separate CRs
- **FR-004**: System MUST support context-based execution (application, component)

#### Ephemeral Cluster Provisioning

- **FR-005**: System MUST provision ephemeral HyperShift cluster via Konflux EaaS StepActions
- **FR-006**: System MUST retrieve cluster credentials (kubeconfig) after provisioning
- **FR-007**: System MUST destroy ephemeral cluster after test completion (pass or fail)
- **FR-008**: System MUST handle provisioning timeout (25 min max)

#### ODH/RHOAI Installation

- **FR-009**: System MUST install ODH operator on ephemeral cluster
- **FR-010**: System MUST create DSC/DSCI with component images from SNAPSHOT
- **FR-011**: System MUST wait for component readiness before test execution
- **FR-012**: System MUST support both ODH (upstream) and RHOAI (downstream) installation

#### Test Execution

- **FR-013**: System MUST execute pytest with configurable marker selection
- **FR-014**: System MUST use the opendatahub-tests container image for test execution
- **FR-015**: System MUST generate JUnit XML test reports
- **FR-016**: System MUST enforce test timeout (configurable, default 30 min for smoke)

#### Artifact Management

- **FR-017**: System MUST collect must-gather on test failure
- **FR-018**: System MUST upload artifacts before cluster destruction
- **FR-019**: System MUST compress must-gather archives

#### Result Reporting

- **FR-020**: System MUST report pass/fail status to Konflux Integration Service
- **FR-021**: System MUST provide test summary in pipeline results
- **FR-022**: System MUST include artifact links in results

### Key Entities

- **IntegrationTestScenario**: CR defining test pipeline reference and configuration
- **Snapshot**: Konflux entity containing built component images
- **Pipeline**: Tekton Pipeline defining test execution workflow
- **ClusterTemplateInstance**: EaaS resource for ephemeral cluster provisioning
- **TestConfiguration**: Parameters passed to pipeline (markers, timeout, distribution)

## Success Criteria

### Measurable Outcomes

- **SC-001**: ITS pipeline triggers successfully for 100% of component builds
- **SC-002**: Ephemeral cluster provisioning succeeds for 95% of pipeline runs
- **SC-003**: Smoke tests complete within 45 minutes (including 15-20 min cluster provisioning)
- **SC-004**: ODH installation succeeds for 98% of pipeline runs
- **SC-005**: Must-gather artifacts are available for 100% of test failures
- **SC-006**: Pipeline failure rate due to infrastructure issues is below 10%
- **SC-007**: SNAPSHOT component images are correctly deployed in 100% of runs

### Quality Gates

- IntegrationTestScenario CR passes Konflux validation
- Pipeline tested manually before enabling as default ITS
- Documentation updated with ITS usage and debugging instructions
- Rollback procedure documented (disable ITS CR)

## Out of Scope (Phase 1)

- Parallel test execution (pytest-xdist) - ephemeral clusters are single-use
- GPU-based tests - ephemeral HyperShift clusters may not have GPU nodes
- Performance/load testing - ITS not suitable for long-running tests
- Multi-cluster test orchestration
- Integration with external test management (Polarion, ReportPortal)
- RHOAI installation (ODH first; RHOAI as Phase 2)

## References

- [Konflux Integration Service](https://github.com/konflux-ci/integration-service)
- [Konflux Documentation - Getting Started](https://konflux-ci.dev/docs/getting-started/)
- [Ephemeral Clusters in Konflux](https://developers.redhat.com/articles/2024/10/28/ephemeral-openshift-clusters-konflux-ci-using-cluster-service-operator)
- [Konflux Pipeline Samples](https://github.com/konflux-ci/pipeline-samples)
- [Konflux Build Definitions](https://github.com/konflux-ci/build-definitions)
