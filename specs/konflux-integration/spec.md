# Feature Specification: Konflux IT Integration for RHOAI Testing

**Feature Branch**: `konflux-integration`
**Created**: 2026-01-08
**Status**: Draft
**Input**: Enable Konflux IT pipelines to drive integration tests against Red Hat OpenShift AI deployments

## Overview

This feature integrates the opendatahub-tests repository with Konflux (Red Hat's Tekton-based CI/CD platform) to enable automated integration testing against RHOAI deployments. The goal is to move from static checks (tox) to full integration test execution in CI pipelines.

## User Scenarios & Testing

### User Story 1 - Smoke Test Execution on PR (Priority: P1)

As a developer submitting a PR, I want smoke tests to run automatically against a RHOAI deployment so that I get fast feedback on whether my changes break core functionality.

**Why this priority**: Smoke tests are the first line of defense. They run quickly (<30 min) and validate core functionality. Without this, developers merge code without integration validation.

**Independent Test**: Can be fully tested by triggering a PR and verifying smoke test results appear in the PR checks within 30 minutes.

**Acceptance Scenarios**:

1. **Given** a PR is opened against the main branch, **When** the Konflux pipeline triggers, **Then** smoke tests (`-m smoke`) execute against a RHOAI cluster and results are reported back to the PR.

2. **Given** smoke tests are running, **When** a test fails, **Then** must-gather artifacts are collected and uploaded as pipeline artifacts.

3. **Given** smoke tests complete, **When** all tests pass, **Then** the PR check shows green status with test summary.

4. **Given** the test container needs to authenticate to the cluster, **When** the pipeline runs, **Then** ServiceAccount-based authentication is used (no user credentials required).

---

### User Story 2 - Tier1 Test Execution on Merge (Priority: P2)

As a release engineer, I want tier1 tests to run automatically when code merges to main so that we validate more comprehensive functionality before releases.

**Why this priority**: Tier1 tests cover frequently used functionality. Running on merge ensures main branch stability without blocking every PR with longer test runs.

**Independent Test**: Can be tested by merging a PR and verifying tier1 tests complete within 2 hours with results published.

**Acceptance Scenarios**:

1. **Given** a PR is merged to main, **When** the merge pipeline triggers, **Then** tier1 tests (`-m tier1`) execute against a RHOAI cluster.

2. **Given** tier1 tests are running, **When** tests use GPU resources, **Then** the pipeline correctly schedules tests on GPU-enabled nodes.

3. **Given** tier1 tests complete, **When** results are available, **Then** a JUnit XML report is generated and stored as a pipeline artifact.

---

### User Story 3 - Parallel Test Execution (Priority: P2)

As a CI operator, I want tests to run in parallel so that pipeline execution time is minimized while maintaining test isolation.

**Why this priority**: Current sequential execution is too slow for CI. Parallel execution with proper isolation is essential for practical CI integration.

**Independent Test**: Can be tested by running a test suite and verifying multiple test workers execute simultaneously with isolated namespaces.

**Acceptance Scenarios**:

1. **Given** a test suite with `parallel` marker, **When** the pipeline runs with parallelism=4, **Then** 4 pytest-xdist workers execute tests concurrently.

2. **Given** parallel tests are running, **When** each test creates resources, **Then** each worker uses a unique namespace to prevent resource conflicts.

3. **Given** parallel execution completes, **When** results are aggregated, **Then** a single consolidated report is produced.

---

### User Story 4 - Configurable Test Suite Selection (Priority: P3)

As a QE engineer, I want to configure which test suites run in different pipeline contexts so that I can balance coverage vs. execution time.

**Why this priority**: Different contexts (PR, merge, nightly, release) need different test coverage. Flexibility enables appropriate testing at each stage.

**Independent Test**: Can be tested by triggering pipelines with different marker configurations and verifying correct test selection.

**Acceptance Scenarios**:

1. **Given** a pipeline is triggered, **When** the `test-markers` parameter is set to `smoke`, **Then** only smoke tests execute.

2. **Given** a nightly pipeline runs, **When** markers are set to `tier1 and tier2`, **Then** both tier1 and tier2 tests execute.

3. **Given** an upgrade test scenario, **When** `pre_upgrade` marker is used, **Then** only pre-upgrade tests run, preserving resources for post-upgrade phase.

---

### User Story 5 - Failure Diagnosis with Must-Gather (Priority: P3)

As a test engineer diagnosing failures, I want must-gather artifacts collected automatically on test failure so that I have the information needed to debug issues.

**Why this priority**: Without diagnostic artifacts, test failures in CI are difficult to investigate. This enables efficient triage.

**Independent Test**: Can be tested by intentionally failing a test and verifying must-gather archive is available in pipeline artifacts.

**Acceptance Scenarios**:

1. **Given** a test fails during execution, **When** the failure is detected, **Then** must-gather is triggered for the relevant namespace.

2. **Given** must-gather completes, **When** artifacts are collected, **Then** they are archived and uploaded to pipeline artifact storage.

3. **Given** multiple tests fail, **When** must-gather runs, **Then** each failure has a separate timestamped archive.

---

### Edge Cases

- What happens when the RHOAI cluster is unavailable at pipeline start?
  - Pipeline should fail fast with clear error message
- How does system handle test timeout?
  - Individual test timeout (configurable, default 10min) and overall pipeline timeout (configurable, default 4h)
- What happens when parallel workers exhaust cluster resources?
  - Resource quota per namespace; tests marked `gpu` run sequentially
- How does system handle flaky tests?
  - Optional retry mechanism (max 2 retries) for marked flaky tests

## Requirements

### Functional Requirements

#### Pipeline Infrastructure

- **FR-001**: System MUST define Tekton Pipeline resources in `.tekton/` directory
- **FR-002**: System MUST build test container image from existing Dockerfile on pipeline trigger
- **FR-003**: System MUST support both PR-triggered and merge-triggered pipeline runs
- **FR-004**: System MUST support manual pipeline triggers with configurable parameters

#### Test Execution

- **FR-005**: System MUST execute pytest with configurable marker selection
- **FR-006**: System MUST support pytest-xdist parallel execution with configurable worker count
- **FR-007**: System MUST isolate each parallel worker in a unique Kubernetes namespace
- **FR-008**: System MUST enforce test timeout at individual test and pipeline level
- **FR-009**: System MUST support both upstream (ODH) and downstream (RHOAI) distributions

#### Authentication & Authorization

- **FR-010**: System MUST authenticate to target cluster using ServiceAccount tokens
- **FR-011**: System MUST NOT require user credentials for pipeline execution
- **FR-012**: System MUST support RBAC templates for test ServiceAccount permissions

#### Artifact Management

- **FR-013**: System MUST generate JUnit XML test reports
- **FR-014**: System MUST collect must-gather on test failure
- **FR-015**: System MUST upload test artifacts to Konflux artifact storage
- **FR-016**: System MUST archive must-gather with compression

#### Configuration

- **FR-017**: System MUST externalize configuration via ConfigMap/Secret
- **FR-018**: System MUST support environment-specific configuration profiles (dev, staging, prod)
- **FR-019**: System MUST validate configuration schema at pipeline start

### Key Entities

- **Pipeline**: Tekton Pipeline definition specifying test execution workflow
- **PipelineRun**: Instance of a pipeline execution with specific parameters
- **Task**: Tekton Task for individual pipeline steps (build, test, collect-artifacts)
- **TestConfiguration**: ConfigMap containing test suite parameters (markers, parallelism, timeout)
- **ClusterCredentials**: Secret containing cluster authentication (ServiceAccount token or kubeconfig)

## Success Criteria

### Measurable Outcomes

- **SC-001**: Smoke tests complete within 30 minutes for 95% of PR pipeline runs
- **SC-002**: Tier1 tests complete within 2 hours for 95% of merge pipeline runs
- **SC-003**: Parallel execution achieves at least 3x speedup compared to sequential execution
- **SC-004**: Must-gather artifacts are available for 100% of test failures
- **SC-005**: Pipeline failure rate due to infrastructure issues (not test failures) is below 5%
- **SC-006**: Zero user credentials are required for pipeline execution (ServiceAccount-only)
- **SC-007**: Test results are visible in PR checks within 5 minutes of pipeline completion

### Quality Gates

- All pipeline definitions pass Tekton lint validation
- Pipeline execution tested in staging environment before production rollout
- Documentation updated with pipeline usage instructions
- Rollback procedure documented and tested

## Out of Scope (Phase 1)

- Ephemeral cluster provisioning (uses pre-existing clusters)
- Multi-cluster test orchestration
- Performance/load testing integration
- Cost optimization for cluster resources
- Integration with external test management systems (Polarion, ReportPortal)
