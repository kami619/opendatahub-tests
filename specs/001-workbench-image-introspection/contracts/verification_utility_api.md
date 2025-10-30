# API Contract: Package Verification Utility

**Module**: `tests.workbenches.utils`
**Function**: `verify_package_import`
**Version**: 1.0.0
**Date**: 2025-10-30

---

## Function Signature

```python
def verify_package_import(
    pod: Pod,
    container_name: str,
    packages: list[str],
    timeout: int = 60,
    collect_diagnostics: bool = True
) -> dict[str, PackageVerificationResult]:
    """
    Verify that specified Python packages are importable in a pod container.

    This function executes 'python -c "import <package>"' for each package
    in the provided list and returns verification results.

    Args:
        pod: Pod instance to execute commands in (from ocp_resources.pod)
        container_name: Name of the container within the pod to target
        packages: List of Python package names to verify (e.g., ["sdg_hub", "numpy"])
        timeout: Maximum time in seconds to wait for each import command (default: 60)
        collect_diagnostics: Whether to collect pod logs on failure (default: True)

    Returns:
        Dictionary mapping package names to PackageVerificationResult objects.
        Example:
        {
            "sdg_hub": PackageVerificationResult(
                package_name="sdg_hub",
                import_successful=True,
                error_message=None,
                ...
            ),
            "missing_pkg": PackageVerificationResult(
                package_name="missing_pkg",
                import_successful=False,
                error_message="ModuleNotFoundError: No module named 'missing_pkg'",
                ...
            )
        }

    Raises:
        ValueError: If packages list is empty or contains invalid identifiers
        PodNotReadyError: If pod is not in Running state
        ContainerNotFoundError: If specified container doesn't exist in pod
        TimeoutError: If command execution exceeds timeout (internal, converted to result)

    Example:
        >>> from ocp_resources.pod import Pod
        >>> from tests.workbenches.utils import verify_package_import
        >>>
        >>> pod = Pod(client=client, namespace="test", name="notebook-0")
        >>> results = verify_package_import(
        ...     pod=pod,
        ...     container_name="notebook",
        ...     packages=["sdg_hub", "instructlab"]
        ... )
        >>> assert all(r.import_successful for r in results.values())
    """
```

---

## Input Validation

### Pre-conditions

| Condition | Validation | Error if Violated |
|-----------|------------|-------------------|
| Pod exists | `pod.exists` returns True | `ResourceNotFoundError` |
| Pod is running | `pod.instance.status.phase == "Running"` | `PodNotReadyError` |
| Container exists | `container_name` in pod spec | `ContainerNotFoundError` |
| Packages non-empty | `len(packages) > 0` | `ValueError("packages list cannot be empty")` |
| Package names valid | Each matches `^[a-zA-Z_][a-zA-Z0-9_]*$` | `ValueError("Invalid package name: {name}")` |
| Timeout positive | `timeout > 0` | `ValueError("timeout must be positive")` |

---

## Command Execution Contract

### For Each Package

**Command Template**:
```bash
python -c "import {package_name}"
```

**Execution Method**:
```python
import shlex
pod.execute(
    container=container_name,
    command=shlex.split(f"python -c 'import {package_name}'")
)
```

**Success Criteria**:
- Return code: 0
- No exception raised

**Failure Detection**:
- `ExecOnPodError` exception caught
- Return code: non-zero
- stderr contains "ModuleNotFoundError" or "ImportError"

---

## Return Value Contract

### PackageVerificationResult Structure

```python
@dataclass
class PackageVerificationResult:
    """Result of a single package import verification."""

    package_name: str
    """Name of the package that was tested."""

    import_successful: bool
    """True if import succeeded, False otherwise."""

    error_message: str | None
    """Error message if import failed, None if successful."""

    command_executed: str
    """Exact command that was executed."""

    execution_time_seconds: float
    """Time taken to execute the command."""

    pod_logs: str | None
    """Pod logs captured on failure (if collect_diagnostics=True), None otherwise."""

    stdout: str
    """Standard output from command execution."""

    stderr: str
    """Standard error from command execution."""
```

### Return Value Guarantees

1. **Dictionary keys match input packages**: `set(result.keys()) == set(packages)`
2. **All results present**: No missing packages in output
3. **Consistent state**: If `import_successful=True`, then `error_message=None`
4. **Error details**: If `import_successful=False`, then `error_message` is non-null
5. **Execution time**: `execution_time_seconds >= 0` and `execution_time_seconds < timeout`

---

## Error Handling Contract

### Exception Table

| Exception | When Raised | Recovery Action |
|-----------|-------------|-----------------|
| `ValueError` | Invalid input parameters | Fix test parametrization |
| `ResourceNotFoundError` | Pod doesn't exist | Check pod creation in fixture |
| `PodNotReadyError` | Pod not in Running state | Ensure `wait_for_condition()` called before verification |
| `ContainerNotFoundError` | Container name mismatch | Verify container name matches notebook name |

### Partial Failure Behavior

**Scenario**: Package 1 imports successfully, Package 2 fails

**Behavior**:
- Function continues execution (does not raise exception)
- Returns results for both packages
- Package 1: `import_successful=True`
- Package 2: `import_successful=False` with error details

**Rationale**: Allows test to report all failures at once rather than stopping at first failure

---

## Performance Contract

### Timing Guarantees

| Operation | Maximum Time | Notes |
|-----------|--------------|-------|
| Single package verification | `timeout` seconds | Default 60s |
| Total function execution | `len(packages) * timeout + 5` seconds | 5s overhead for setup |
| Pod status check | 2 seconds | Pre-flight validation |

### Resource Usage

- **Memory**: O(n) where n = number of packages (stores results in dict)
- **Network**: One pod exec API call per package
- **Pod Load**: Minimal - short-lived Python import commands

---

## Diagnostic Information Contract

### When `collect_diagnostics=True`

On verification failure, the function collects:

1. **Pod logs**: Last 100 lines from target container
   ```python
   pod_logs = pod.log(container=container_name, tail_lines=100)
   ```

2. **Command output**: Full stdout and stderr
   ```python
   result.stdout = "..."  # From pod.execute()
   result.stderr = "..."  # From pod.execute() or ExecOnPodError
   ```

3. **Container status**: Verification result includes status check
   ```python
   container_ready = pod.instance.status.containerStatuses[i].ready
   ```

### When `collect_diagnostics=False`

- `pod_logs = None` in all results
- Faster execution (no log retrieval)
- Use when running many tests in parallel

---

## Compatibility Contract

### Version Compatibility

| Python Version | Supported | Notes |
|----------------|-----------|-------|
| 3.13 | ✓ | Primary target |
| 3.12 | ✓ | Should work (union type hints) |
| 3.11 | ✓ | Should work |
| < 3.11 | ✗ | Type hints incompatible |

### Dependency Requirements

```python
# Required
from ocp_resources.pod import Pod, ExecOnPodError
from kubernetes.dynamic import DynamicClient
import shlex
from dataclasses import dataclass
from time import time

# Optional (for enhanced error handling)
from simple_logger.logger import get_logger
```

---

## Example Usage Patterns

### Pattern 1: Basic Verification

```python
from tests.workbenches.utils import verify_package_import

results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["sdg_hub"]
)

assert results["sdg_hub"].import_successful, \
    f"sdg_hub not available: {results['sdg_hub'].error_message}"
```

### Pattern 2: Multiple Packages with Detailed Errors

```python
results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["sdg_hub", "instructlab", "numpy"],
    timeout=90
)

failed_packages = [
    name for name, result in results.items()
    if not result.import_successful
]

if failed_packages:
    error_details = "\n".join([
        f"- {name}: {results[name].error_message}"
        for name in failed_packages
    ])
    pytest.fail(f"Packages not available:\n{error_details}")
```

### Pattern 3: Performance Monitoring

```python
results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["large_package"],
    timeout=120
)

import_time = results["large_package"].execution_time_seconds
assert import_time < 10, \
    f"Package import too slow: {import_time}s (expected <10s)"
```

### Pattern 4: Skip Diagnostics for Speed

```python
# For smoke tests or parallel execution
results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["sdg_hub"],
    collect_diagnostics=False  # Faster, no log collection
)
```

---

## Testing the Utility

### Unit Test Contract

```python
def test_verify_package_import_success(mock_pod):
    """Test successful package verification."""
    mock_pod.execute.return_value = ""  # Success: empty output

    results = verify_package_import(
        pod=mock_pod,
        container_name="test",
        packages=["numpy"]
    )

    assert results["numpy"].import_successful
    assert results["numpy"].error_message is None
    mock_pod.execute.assert_called_once()

def test_verify_package_import_failure(mock_pod):
    """Test package import failure."""
    mock_pod.execute.side_effect = ExecOnPodError("ModuleNotFoundError")

    results = verify_package_import(
        pod=mock_pod,
        container_name="test",
        packages=["missing"]
    )

    assert not results["missing"].import_successful
    assert "ModuleNotFoundError" in results["missing"].error_message
```

---

## Backward Compatibility

### Version 1.0.0 Guarantees

- Function signature will not change (parameters may be added with defaults)
- Return type structure will remain compatible
- `PackageVerificationResult` dataclass fields will not be removed
- New fields may be added to `PackageVerificationResult` (with defaults)

### Migration Path

If signature changes in future versions:
```python
# Old call (v1.0.0)
verify_package_import(pod, "container", ["pkg"])

# New call (v2.0.0 - hypothetical)
verify_package_import(pod, "container", ["pkg"], new_param=default_value)
```

---

## Security Considerations

### Input Sanitization

**Package Name Validation**:
- Must match Python identifier rules
- No shell metacharacters allowed
- Prevents command injection via package name

**Command Construction**:
- Uses `shlex.split()` for proper escaping
- Package names validated before interpolation
- No user input directly in command string

### Execution Context

- Runs in unprivileged container
- No filesystem modifications
- Read-only package import only
- Cannot escape container sandbox

---

## Observability Contract

### Logging

```python
LOGGER.info(f"Verifying {len(packages)} packages in {container_name}")
LOGGER.debug(f"Executing: {command_executed}")
LOGGER.info(f"Package {package_name}: {'✓' if success else '✗'}")
LOGGER.warning(f"Package verification failed: {error_message}")
```

### Metrics (Future Enhancement)

- `package_verification_duration_seconds{package, result}`
- `package_verification_total{package, result}`
- `package_verification_errors_total{error_type}`

---

## Change Log

### Version 1.0.0 (2025-10-30)
- Initial API definition
- Basic package import verification
- Diagnostic collection support
- Multiple package support
