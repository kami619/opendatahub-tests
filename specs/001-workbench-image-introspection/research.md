# Research: Workbench Custom Image Introspection Testing

**Date**: 2025-10-30
**Feature**: Workbench Custom Image Introspection Testing

## Purpose

This research document consolidates findings on technical approaches, best practices, and implementation patterns for enabling custom workbench image validation with package introspection in the existing pytest-based test framework.

---

## 1. Pod Command Execution Patterns

### Decision: Use `Pod.execute()` from openshift-python-wrapper

**Rationale**: The codebase already uses `Pod.execute()` extensively across 20+ test files for executing commands inside running containers. This method provides:
- Native integration with `ocp_resources.Pod` class
- Built-in error handling via `ExecOnPodError` exception
- Container-specific execution support
- Return code handling with `ignore_rc` parameter

**Implementation Pattern**:
```python
from ocp_resources.pod import Pod, ExecOnPodError
import shlex

# Execute package import verification
try:
    result = pod.execute(
        container="notebook-container-name",
        command=shlex.split("python -c 'import sdg_hub'")
    )
except ExecOnPodError as e:
    # Handle import failure - package not found
    raise PackageNotFoundError(f"Package 'sdg_hub' not importable: {e}")
```

**Examples in Codebase**:
- `tests/model_serving/model_server/storage/pvc/test_kserve_pvc_write_access.py:51-55` - Permission validation
- `tests/model_serving/model_server/multi_node/utils.py:30-50` - Command output parsing
- `tests/model_registry/negative_tests/utils.py:16-33` - MySQL command execution

**Alternatives Considered**:
- `kubernetes.stream.stream()` API - Rejected because openshift-python-wrapper provides higher-level abstraction and is already used throughout the codebase
- Port-forwarding + HTTP API - Rejected as overcomplicated for simple package verification

---

## 2. Pod Readiness Waiting Patterns

### Decision: Use `pod.wait()` + `pod.wait_for_condition()` pattern with 10-minute timeout

**Rationale**: This two-stage approach is the established pattern in the codebase (see `tests/workbenches/notebook-controller/test_spawning.py:45-46`):
1. `pod.wait()` - Ensures pod exists
2. `pod.wait_for_condition(condition=Pod.Condition.READY, status=Pod.Condition.Status.TRUE)` - Waits for pod readiness

**Timeout Configuration**:
- 10 minutes (600 seconds) for custom image pods to accommodate large image pulls
- 1 minute (60 seconds) for command execution to prevent indefinite hangs
- Use `utilities/constants.py::Timeout.TIMEOUT_10MIN` constant for consistency

**Implementation**:
```python
from ocp_resources.pod import Pod
from utilities.constants import Timeout

# Wait for pod to reach Running state
notebook_pod = Pod(
    client=unprivileged_client,
    namespace=notebook.namespace,
    name=f"{notebook.name}-0",
)
notebook_pod.wait()
notebook_pod.wait_for_condition(
    condition=Pod.Condition.READY,
    status=Pod.Condition.Status.TRUE,
    timeout=Timeout.TIMEOUT_10MIN
)
```

**Alternatives Considered**:
- `TimeoutSampler` with custom logic - Rejected as unnecessarily complex when built-in `wait_for_condition()` suffices
- Shorter timeout (5 minutes) - Rejected due to spec requirement FR-003 specifying 10 minutes for large custom images

---

## 3. Pytest Fixture Customization for Custom Images

### Decision: Add optional `custom_image` parameter to `default_notebook` fixture using `request.param.get()` pattern

**Rationale**: The existing `default_notebook` fixture already uses the `.get()` pattern for optional `auth_annotations` parameter (conftest.py:57). This approach:
- Maintains 100% backward compatibility - existing tests work unchanged
- Follows established codebase conventions
- Requires minimal code changes (3-5 lines)
- Provides clear upgrade path for new test cases

**Implementation Pattern**:
```python
@pytest.fixture(scope="function")
def default_notebook(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    minimal_image: str,
) -> Generator[Notebook, None, None]:
    namespace = request.param["namespace"]
    name = request.param["name"]
    auth_annotations = request.param.get("auth_annotations", {})

    # NEW: Optional custom image parameter
    custom_image = request.param.get("custom_image", None)

    # Use custom_image if provided, otherwise fall back to minimal_image
    if custom_image:
        minimal_image_path = custom_image  # Assume full registry path
    else:
        # Existing logic for default minimal_image
        minimal_image_path = (
            f"{INTERNAL_IMAGE_REGISTRY_PATH}/{py_config['applications_namespace']}/{minimal_image}"
            if internal_image_registry
            else ":" + minimal_image.rsplit(":", maxsplit=1)[1]
        )

    # Rest of notebook creation...
```

**Test Parametrization Example**:
```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        pytest.param(
            {"name": "test-custom", "add-dashboard-label": True},
            {"name": "test-custom"},
            {
                "namespace": "test-custom",
                "name": "test-custom",
                "custom_image": "quay.io/org/sdg-hub-notebook:2025.1",
            },
            id="custom_sdg_hub_image",
        )
    ],
    indirect=True,
)
def test_custom_image_validation(self, default_notebook: Notebook):
    # Test implementation
```

**Alternatives Considered**:
- Separate `custom_notebook` fixture - Rejected due to code duplication
- Override `minimal_image` fixture - Rejected as it would affect all tests in scope
- Helper function for image resolution - Deferred to implementation phase if complexity increases

---

## 4. Pod Log Retrieval and Error Handling

### Decision: Use `pod.log(container="container-name")` for diagnostic output + comprehensive error categorization

**Rationale**: The codebase demonstrates mature error handling patterns in `utilities/infra.py:760-816` with categorization of container states:
- **Waiting states**: `ImagePullBackOff`, `CrashLoopBackOff`, `InvalidImageName`, `ErrImagePull`
- **Terminated states**: `Error`, `OOMKilled`, `CrashLoopBackOff`
- **Pod phases**: `Failed`, `Pending`

**Implementation Pattern**:
```python
from ocp_resources.pod import Pod
from timeout_sampler import TimeoutExpiredError

try:
    notebook_pod.wait_for_condition(
        condition=Pod.Condition.READY,
        status=Pod.Condition.Status.TRUE,
        timeout=Timeout.TIMEOUT_10MIN
    )
except TimeoutExpiredError:
    # Collect diagnostic information
    pod_status = notebook_pod.instance.status
    pod_phase = pod_status.phase

    # Get logs from main container
    try:
        pod_logs = notebook_pod.log(container=notebook_name)
    except Exception:
        pod_logs = "Could not retrieve logs"

    # Check for specific error states
    error_reason = None
    if pod_status.containerStatuses:
        for container_status in pod_status.containerStatuses:
            if waiting := container_status.state.waiting:
                error_reason = waiting.reason

    raise PodNotReadyError(
        f"Pod failed to reach Ready state. "
        f"Phase: {pod_phase}, Reason: {error_reason}, "
        f"Logs: {pod_logs[:500]}"
    )
```

**Error Message Structure** (from spec FR-007, FR-012):
1. **ImagePullBackOff**: "Failed to pull custom image. Verify registry access and image URL: {image_url}"
2. **Package Import Failure**: "Package '{package}' not importable. ModuleNotFoundError: {error}. Installed packages: {package_list}"
3. **Pod Timeout**: "Pod did not reach Running state within 10 minutes. Phase: {phase}, Events: {events}"

**Alternatives Considered**:
- Minimal error messages - Rejected per spec requirement for actionable diagnostic information
- Pod events retrieval - Deferred to enhancement (not required for MVP)

---

## 5. Package Verification Utility Design

### Decision: Create reusable `verify_package_import()` utility function in `tests/workbenches/utils.py`

**Rationale**: The spec requires a reusable utility (FR-006) that accepts package names as parameters. Placing it in utils.py alongside existing `get_username()` helper maintains module organization.

**Function Signature**:
```python
def verify_package_import(
    pod: Pod,
    container_name: str,
    packages: list[str],
    timeout: int = 60
) -> dict[str, bool]:
    """
    Verify that specified Python packages are importable in a pod container.

    Args:
        pod: Pod instance to execute commands in
        container_name: Name of the container to target
        packages: List of package names to verify (e.g., ["sdg_hub", "numpy"])
        timeout: Command execution timeout in seconds (default 60)

    Returns:
        Dictionary mapping package names to import success status

    Raises:
        ExecOnPodError: If command execution fails (pod/container not available)
        PackageVerificationError: If any packages fail to import
    """
```

**Example Usage**:
```python
from tests.workbenches.utils import verify_package_import

# Verify single package
results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["sdg_hub"]
)
assert results["sdg_hub"], "sdg_hub package not available"

# Verify multiple packages
results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["sdg_hub", "instructlab", "numpy"]
)
```

**Alternatives Considered**:
- Test helper method in test class - Rejected as it wouldn't be reusable across test classes
- Separate verification module - Rejected as overkill for MVP scope

---

## 6. Test Marker Strategy

### Decision: Use `@pytest.mark.sanity` and `@pytest.mark.slow` for custom image tests

**Rationale**: From spec FR-009 - custom image validation should NOT be smoke tests due to:
- Longer execution time (10+ minutes)
- Dependency on external registries
- Resource-intensive operations

**Marker Configuration**:
```python
@pytest.mark.sanity  # Integration-level validation
@pytest.mark.slow    # Execution time > 5 minutes
@pytest.mark.parametrize(...)
def test_custom_image_package_verification(...):
    pass
```

**Existing Smoke Tests** (for reference):
- `test_spawning.py::test_create_simple_notebook` - Uses minimal image, fast execution
- `test_spawning.py::test_auth_container_resource_customization` - Configuration validation

**Alternatives Considered**:
- `@pytest.mark.smoke` - Rejected per spec requirement
- Custom marker `@pytest.mark.custom_image` - Deferred (not required for MVP)

---

## 7. Container Name Resolution

### Decision: Extract container name from Notebook spec during pod creation

**Rationale**: The notebook pod has multiple containers (main notebook + kube-rbac-proxy sidecar). The package verification must target the correct container.

**Implementation**:
```python
# In test
notebook_pod = Pod(
    client=unprivileged_client,
    namespace=default_notebook.namespace,
    name=f"{default_notebook.name}-0",
)
notebook_pod.wait_for_condition(...)

# The main container name matches the notebook name
container_name = default_notebook.name

# Execute in the correct container
result = notebook_pod.execute(
    container=container_name,
    command=shlex.split("python -c 'import sdg_hub'")
)
```

**Container Structure** (from conftest.py:112-144):
- Container 1: `{notebook_name}` - Main notebook container (Jupyter)
- Container 2: `kube-rbac-proxy` - Authentication sidecar

---

## 8. Documentation Requirements

### Decision: Enhance `tests/workbenches/README.md` with custom image testing section

**Rationale**: Spec requirements FR-010 and User Story 4 mandate documentation for:
- Test structure and ownership boundaries
- Adding new custom image tests
- Required information from image teams

**Documentation Structure**:
```markdown
# Workbench Tests

## Directory Structure
- `conftest.py` - Shared fixtures (notebooks, PVCs, images)
- `utils.py` - Helper functions (username, package verification)
- `notebook-controller/`
  - `test_spawning.py` - Basic notebook spawning tests
  - `test_custom_images.py` - Custom image validation tests

## Custom Image Validation Tests

### Purpose
Validate that custom workbench images contain required packages and configurations.

### Adding a New Custom Image Test
1. Obtain image URL and package list from workbench image team
2. Add parametrized test case to `test_custom_images.py`
3. Specify custom_image and packages to verify
4. Run test: `pytest tests/workbenches/notebook-controller/test_custom_images.py -m sanity`

### Example
[Code example here]

### Ownership
- QE Team: Test framework, fixtures, utilities
- Workbench Image Team: Image builds, package specifications
```

---

## 9. Test Timeout Configuration

### Decision: Use adaptive timeout strategy based on operation type

**Rationale**: Different operations have different time requirements (from spec SC-002):
- Pod readiness: 10 minutes (large image pulls)
- Package verification: 1 minute (command execution)
- Total test time: 12 minutes maximum

**Timeout Constants** (from `utilities/constants.py`):
```python
Timeout.TIMEOUT_1MIN = 60
Timeout.TIMEOUT_10MIN = 600
```

**Implementation**:
```python
# Phase 1: Pod readiness (10 min)
notebook_pod.wait_for_condition(
    condition=Pod.Condition.READY,
    status=Pod.Condition.Status.TRUE,
    timeout=Timeout.TIMEOUT_10MIN
)

# Phase 2: Package verification (1 min per package)
result = notebook_pod.execute(
    container=container_name,
    command=shlex.split("python -c 'import sdg_hub'"),
    timeout=Timeout.TIMEOUT_1MIN  # Note: May need custom timeout parameter
)
```

---

## 10. Critical Blocker Resolution

### Decision: Coordinate with workbench image team for sdg_hub image URL

**Status**: BLOCKER - Per spec "Dependencies and Blockers" section

**Required Information**:
- Full registry URL (e.g., `quay.io/opendatahub/sdg-hub-notebook:2025.1`)
- Image tag/version strategy
- Required packages list
- Expected update frequency

**Action Items**:
1. Contact workbench image team for image details
2. Verify test cluster has registry access (pull permissions)
3. Document image URL in test parametrization
4. Add image URL to test documentation

---

## Summary of Key Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| Command Execution | `Pod.execute()` from openshift-python-wrapper | Established pattern, native integration |
| Pod Waiting | Two-stage: `wait()` + `wait_for_condition()` | Existing pattern in workbenches tests |
| Image Parametrization | Optional `custom_image` in `request.param` | Backward compatible, minimal changes |
| Error Handling | Categorized states + diagnostic logs | Production-ready patterns from utilities |
| Verification Utility | Reusable function in `utils.py` | Follows spec requirement FR-006 |
| Test Markers | `@pytest.mark.sanity` + `@pytest.mark.slow` | Spec requirement FR-009 |
| Timeouts | 10min pod, 1min command | Spec requirements FR-003, FR-004 |
| Documentation | Enhanced workbenches README | Spec requirement FR-010 |

---

## Next Steps (Phase 1: Design & Contracts)

1. Generate data model for test entities (Notebook, Pod, VerificationResult)
2. Define verification utility API contract
3. Create quickstart guide for adding custom image tests
4. Update agent context with research findings
