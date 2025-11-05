# Workbench Tests

This directory contains tests for OpenDataHub/RHOAI workbench functionality, including notebook spawning, custom image validation, and package introspection capabilities.

## Directory Structure

```
tests/workbenches/
├── README.md                      # This file - documentation and usage guide
├── __init__.py                    # Python package marker
├── conftest.py                    # Shared fixtures (notebooks, PVCs, images)
├── utils.py                       # Helper functions (username, package verification)
└── notebook-controller/
    ├── test_spawning.py           # Basic notebook spawning tests
    └── test_custom_images.py      # Custom image validation tests
```

## Fixtures

### Shared Fixtures (conftest.py)

#### `minimal_image`
Provides the name of a minimal workbench image for testing.
- **Scope**: function
- **Returns**: Image name string (e.g., `"s2i-minimal-notebook:2025.2"`)
- **Usage**: Automatically used by `default_notebook` fixture

#### `users_persistent_volume_claim`
Creates a PersistentVolumeClaim for notebook storage.
- **Scope**: function
- **Parameters**: Requires `name` in `request.param`
- **Cleanup**: Automatic via context manager
- **Usage**: Pass as indirect parametrize argument

#### `default_notebook`
Creates a Notebook custom resource with optional custom image support.
- **Scope**: function
- **Parameters** (via `request.param`):
  - `namespace` (required): Namespace for notebook
  - `name` (required): Notebook name
  - `auth_annotations` (optional): Dict of auth sidecar annotations
  - `custom_image` (optional): Full custom image URL with tag (e.g., `"quay.io/org/image:tag"`)
- **Cleanup**: Automatic via context manager
- **Usage**: Pass as indirect parametrize argument

**Example: Default minimal image**
```python
pytest.param(
    {"name": "test-namespace", "add-dashboard-label": True},
    {"name": "test-pvc"},
    {"namespace": "test-namespace", "name": "test-notebook"},
    id="simple_notebook"
)
```

**Example: Custom workbench image**
```python
pytest.param(
    {"name": "test-custom", "add-dashboard-label": True},
    {"name": "test-custom"},
    {
        "namespace": "test-custom",
        "name": "test-custom",
        "custom_image": "quay.io/org/custom-notebook:v1.0",
    },
    id="custom_image_test"
)
```

## Utility Functions (utils.py)

### `get_username(dyn_client: DynamicClient) -> str | None`
Gets the current username from the Kubernetes cluster.
- **Usage**: Automatically called by `default_notebook` fixture
- **Returns**: Username string or None if unavailable

### `verify_package_import(pod, container_name, packages, timeout=60, collect_diagnostics=True)`
Verifies that Python packages are importable in a pod container.
- **Parameters**:
  - `pod`: Pod instance from `ocp_resources.pod.Pod`
  - `container_name`: Target container name (usually matches notebook name)
  - `packages`: List of Python package names to verify
  - `timeout`: Command execution timeout in seconds (default: 60)
  - `collect_diagnostics`: Whether to collect pod logs on failure (default: True)
- **Returns**: Dict mapping package names to `PackageVerificationResult` objects
- **Raises**: `ValueError` for invalid input, `RuntimeError` if pod not ready

**Example**:
```python
from tests.workbenches.utils import verify_package_import

results = verify_package_import(
    pod=notebook_pod,
    container_name="test-notebook",
    packages=["numpy", "pandas"],
    timeout=60
)

# Check results
for package, result in results.items():
    if not result.import_successful:
        print(f"{package} failed: {result.error_message}")
```

---

## Custom Image Validation Tests

### Purpose
Validate that custom workbench images contain required packages and configurations before release. This prevents runtime errors and ensures images meet specifications.

### Test Location
`tests/workbenches/notebook-controller/test_custom_images.py`

### Test Markers
- `@pytest.mark.sanity` - Integration-level validation
- `@pytest.mark.slow` - Execution time > 5 minutes (typically 8-12 minutes)

### What Gets Tested
1. **Image Pull**: Workbench can pull custom image from registry
2. **Pod Startup**: Pod starts and reaches Ready state within 10 minutes
3. **Package Import**: Required Python packages are importable
4. **Error Diagnostics**: Clear error messages when validation fails

---

## Adding a New Custom Image Test

Follow these steps to add validation for a new custom workbench image.

### Step 1: Gather Information

Before writing the test, obtain from the workbench image team:
- ✅ Full image URL with tag (e.g., `quay.io/org/custom-image:v2.0`)
- ✅ List of required packages to verify (e.g., `["package1", "package2"]`)
- ✅ Any special resource requirements (CPU, memory, GPU)

### Step 2: Add Test Parametrization

Open `tests/workbenches/notebook-controller/test_custom_images.py` and add a new `pytest.param` entry:

```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        # Existing test cases...

        # YOUR NEW TEST CASE
        # Test Case: Your Image Name
        # Image: quay.io/org/your-image:v1.0
        # Required Packages: package1, package2
        # Purpose: Brief description
        # Contact: image-team@example.com
        pytest.param(
            {
                "name": "test-your-image",       # Must be unique
                "add-dashboard-label": True,
            },
            {
                "name": "test-your-image",       # Must match above
            },
            {
                "namespace": "test-your-image",   # Must match above
                "name": "test-your-image",       # Must match above
                "custom_image": "quay.io/org/your-image:v1.0",  # Your image URL
            },
            id="your_image_test",                # Descriptive test ID (snake_case)
        ),
    ],
    indirect=True,
)
def test_custom_image_package_verification(...):
    # Test implementation (no changes needed)
```

### Step 3: Update Package Verification Logic

In the same file, find the package verification section (around line 140) and add your packages:

```python
test_id = request.node.callspec.id
if "your_image_test" in test_id:
    packages_to_verify = ["package1", "package2"]  # Your packages
elif "sdg_hub" in test_id:
    packages_to_verify = ["sdg_hub", "instructlab"]
# ... other cases
```

### Step 4: Run the Test

```bash
# Run your specific test
pytest tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[your_image_test] -v

# Run all custom image tests
pytest tests/workbenches/notebook-controller/test_custom_images.py -v

# Run with sanity marker
pytest -m sanity tests/workbenches/notebook-controller/ -v
```

### Step 5: Interpret Results

**Success (Expected duration: 8-12 minutes)**
```
test_custom_images.py::...::test_custom_image_package_verification[your_image_test] PASSED
```

**Failure: Package Not Found**
```
AssertionError: The following packages are not importable:
  ❌ missing_package:
     Error: ModuleNotFoundError: No module named 'missing_package'
```
→ **Action**: Contact image team to add missing package

**Failure: Image Pull Error**
```
AssertionError: Pod failed to reach Ready state
  ⚠️  ImagePullBackOff: Failed to pull custom image
```
→ **Action**: Verify image URL and registry access

---

## Ownership Boundaries

### QE Team Responsibilities
- ✅ Test framework maintenance (`conftest.py`, `utils.py`)
- ✅ Test case implementation (`test_custom_images.py`)
- ✅ Test execution and reporting
- ✅ Documentation updates

### Workbench Image Team Responsibilities
- ✅ Image builds and registry management
- ✅ Package installation and versioning
- ✅ Providing image URLs and package lists
- ✅ Image updates and maintenance

### Collaboration Required
- 🤝 Image URL coordination (blocker for test implementation)
- 🤝 Package list specifications
- 🤝 Failure investigation (QE provides diagnostics, Image team fixes issues)
- 🤝 Test parametrization updates when new images are released

---

## Troubleshooting

### Common Failure Scenarios

#### 1. Test times out during pod readiness
**Symptom**: `TimeoutExpiredError` after 10 minutes
**Possible Causes**:
- Large image size (> 5GB)
- Registry throttling or network issues
- Image doesn't exist or is inaccessible

**Solutions**:
```bash
# Check image size
podman inspect quay.io/org/image:tag | grep Size

# Test image pull manually
oc run test-pull --image=quay.io/org/image:tag --rm -it -n test-namespace

# Check cluster events
oc get events -n test-namespace --sort-by='.lastTimestamp'
```

#### 2. Package import fails but package should exist
**Symptom**: `ModuleNotFoundError` for installed package
**Possible Causes**:
- Package name mismatch (pip name vs import name)
- Wrong Python environment
- Missing system dependencies

**Solutions**:
```bash
# Test locally
podman run -it quay.io/org/image:tag python -c 'import package_name'

# Check installed packages
podman run -it quay.io/org/image:tag pip list | grep package

# Note: Some packages have different names:
# - pip install: pillow → import: PIL
# - pip install: scikit-learn → import: sklearn
```

#### 3. Permission errors during test
**Symptom**: `PermissionError` or `OSError`
**Possible Causes**:
- Package requires write access during import
- Home directory not writable
- Incorrect file permissions in image

**Solutions**:
- Contact image team to fix permissions
- Verify package doesn't require write access during import

### Debug Commands

```bash
# Get detailed test output
pytest tests/workbenches/notebook-controller/test_custom_images.py -v -s

# Check notebook pod status
oc get pods -n test-namespace
oc describe pod notebook-name-0 -n test-namespace
oc logs notebook-name-0 -c notebook-name -n test-namespace

# Check notebook CR
oc get notebook notebook-name -n test-namespace -o yaml

# Check workbench controller logs
oc logs -l app=notebook-controller -n opendatahub
```

---

## Running Tests

### Run All Workbench Tests
```bash
pytest tests/workbenches/ -v
```

### Run Only Smoke Tests (Fast)
```bash
pytest -m smoke tests/workbenches/ -v
```

### Run Only Sanity Tests (Includes Custom Images)
```bash
pytest -m sanity tests/workbenches/ -v
```

### Run Specific Test File
```bash
pytest tests/workbenches/notebook-controller/test_spawning.py -v
pytest tests/workbenches/notebook-controller/test_custom_images.py -v
```

### Run Single Test Case
```bash
pytest tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[datascience_image] -v
```

---

## Best Practices

### DO ✅
- Use versioned image tags (e.g., `v2.0`) not `latest`
- Test 3-5 key packages per image (not all packages)
- Add descriptive comments above test parametrization
- Use unique namespace names to avoid test conflicts
- Document image team contacts in test comments
- Run tests locally before committing

### DON'T ❌
- Use `latest` tags in production tests (non-reproducible)
- Test standard library packages (`sys`, `os` - always present)
- Skip namespace uniqueness (causes parallel test failures)
- Hardcode timeouts (use `Timeout` constants from `utilities.constants`)
- Ignore test failures (investigate root cause)
- Modify shared fixtures without verifying backward compatibility

---

## Performance Expectations

| Test Type | Expected Duration | Timeout |
|-----------|------------------|---------|
| Smoke (test_spawning.py) | 2-5 minutes | 5 minutes |
| Custom Image (small < 2GB) | 5-8 minutes | 12 minutes |
| Custom Image (large > 5GB) | 8-12 minutes | 15 minutes |
| Full Suite (all workbench tests) | 15-30 minutes | N/A |

**Breakdown** (for custom image tests):
- Pod creation: 5-10 seconds
- Image pull + pod startup: 5-10 minutes (varies by image size)
- Package verification: 1-2 minutes (1 second per package)
- Cleanup: 10-30 seconds

---

## Additional Resources

- **Spec Document**: `specs/001-workbench-image-introspection/spec.md`
- **Quickstart Guide**: `specs/001-workbench-image-introspection/quickstart.md`
- **API Contracts**: `specs/001-workbench-image-introspection/contracts/`
- **Test Planning**: `specs/001-workbench-image-introspection/plan.md`

---

## Support

- **Test Framework Issues**: QE Team
- **Image Build Issues**: Workbench Image Team
- **Registry Access**: Platform Team
- **Test Infrastructure**: CI/CD Team

For questions or issues, refer to team contacts documented in test case comments.
