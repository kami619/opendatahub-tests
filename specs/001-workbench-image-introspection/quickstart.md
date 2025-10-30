# Quickstart Guide: Adding Custom Image Validation Tests

**Audience**: QE Engineers, Workbench Image Team Members
**Time to Complete**: 15 minutes
**Prerequisites**: Access to test repository, custom workbench image URL

---

## Overview

This guide shows you how to add a new test case to validate a custom workbench image with package introspection. You'll learn how to configure test parametrization, specify packages to verify, and run the validation.

---

## Step 1: Gather Required Information

Before writing the test, collect this information from the workbench image team:

| Information | Example | Where to Get It |
|-------------|---------|-----------------|
| **Image URL** | `quay.io/opendatahub/sdg-hub-notebook:2025.1` | Image team, Quay.io repository |
| **Registry** | `quay.io` | Part of image URL |
| **Image Tag** | `2025.1` or `latest` | Image team versioning strategy |
| **Required Packages** | `["sdg_hub", "instructlab"]` | Image team package specifications |
| **Optional: GPU Required** | `true` or `false` | Image team hardware requirements |

**Tip**: Ask the image team for a versioned tag (e.g., `2025.1`) rather than `latest` to ensure reproducible tests.

---

## Step 2: Open the Test File

Navigate to the custom image test file:

```bash
cd tests/workbenches/notebook-controller/
# If test_custom_images.py doesn't exist yet, create it from template (see Step 3)
vim test_custom_images.py
```

---

## Step 3: Add Your Test Case

### Option A: Add to Existing Test Method

If `test_custom_images.py` already exists, add your parameters to the existing parametrize decorator:

```python
@pytest.mark.sanity
@pytest.mark.slow
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        # Existing test cases...

        # YOUR NEW TEST CASE
        pytest.param(
            {
                "name": "test-your-image",  # Change: Unique namespace name
                "add-dashboard-label": True,
            },
            {
                "name": "test-your-image",  # Change: Match namespace name
            },
            {
                "namespace": "test-your-image",  # Change: Match namespace name
                "name": "test-your-image",      # Change: Match namespace name
                "custom_image": "quay.io/org/your-image:tag",  # Change: Your image URL
            },
            id="your_descriptive_id",  # Change: Descriptive test ID
        ),
    ],
    indirect=True,
)
def test_custom_image_package_verification(
    self,
    unprivileged_client: DynamicClient,
    unprivileged_model_namespace: Namespace,
    users_persistent_volume_claim: PersistentVolumeClaim,
    default_notebook: Notebook,
):
    """Test custom workbench image package availability."""
    # Implementation already exists - no changes needed
```

### Option B: Create New Test File

If `test_custom_images.py` doesn't exist, create it with this template:

```python
"""Custom workbench image validation tests."""

import pytest

from kubernetes.dynamic.client import DynamicClient
from ocp_resources.pod import Pod
from ocp_resources.namespace import Namespace
from ocp_resources.notebook import Notebook
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from tests.workbenches.utils import verify_package_import
from utilities.constants import Timeout


class TestCustomImageValidation:
    """Validate custom workbench images with package introspection."""

    @pytest.mark.sanity
    @pytest.mark.slow
    @pytest.mark.parametrize(
        "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
        [
            pytest.param(
                {
                    "name": "test-sdg-hub",
                    "add-dashboard-label": True,
                },
                {
                    "name": "test-sdg-hub",
                },
                {
                    "namespace": "test-sdg-hub",
                    "name": "test-sdg-hub",
                    "custom_image": "quay.io/opendatahub/sdg-hub-notebook:2025.1",
                },
                id="sdg_hub_image",
            ),
        ],
        indirect=True,
    )
    def test_custom_image_package_verification(
        self,
        unprivileged_client: DynamicClient,
        unprivileged_model_namespace: Namespace,
        users_persistent_volume_claim: PersistentVolumeClaim,
        default_notebook: Notebook,
    ):
        """
        Validate that custom workbench image contains required packages.

        This test:
        1. Spawns a workbench with the specified custom image
        2. Waits for the pod to reach Ready state (up to 10 minutes)
        3. Executes package import verification commands
        4. Asserts that all required packages are importable
        """
        # Wait for notebook pod to be created and reach Ready state
        notebook_pod = Pod(
            client=unprivileged_client,
            namespace=default_notebook.namespace,
            name=f"{default_notebook.name}-0",
        )
        notebook_pod.wait()
        notebook_pod.wait_for_condition(
            condition=Pod.Condition.READY,
            status=Pod.Condition.Status.TRUE,
            timeout=Timeout.TIMEOUT_10MIN,
        )

        # Verify packages are importable
        packages_to_verify = ["sdg_hub", "instructlab"]  # Customize per image
        results = verify_package_import(
            pod=notebook_pod,
            container_name=default_notebook.name,
            packages=packages_to_verify,
            timeout=Timeout.TIMEOUT_1MIN,
        )

        # Assert all packages imported successfully
        failed_packages = [
            name for name, result in results.items() if not result.import_successful
        ]

        assert not failed_packages, (
            f"The following packages are not importable in {default_notebook.name}:\n"
            + "\n".join([
                f"  - {name}: {results[name].error_message}"
                for name in failed_packages
            ])
        )
```

---

## Step 4: Customize for Your Image

### 4.1 Update Test Parameters

Replace these fields with your values:

```python
pytest.param(
    {
        "name": "test-YOUR-IMAGE-NAME",  # ← Change this
        "add-dashboard-label": True,     # ← Keep this
    },
    {
        "name": "test-YOUR-IMAGE-NAME",  # ← Match above
    },
    {
        "namespace": "test-YOUR-IMAGE-NAME",  # ← Match above
        "name": "test-YOUR-IMAGE-NAME",       # ← Match above
        "custom_image": "YOUR-FULL-IMAGE-URL",  # ← Your image URL
    },
    id="your_test_id",  # ← Descriptive ID (snake_case)
),
```

**Example**:
```python
pytest.param(
    {"name": "test-ml-toolkit", "add-dashboard-label": True},
    {"name": "test-ml-toolkit"},
    {
        "namespace": "test-ml-toolkit",
        "name": "test-ml-toolkit",
        "custom_image": "quay.io/myorg/ml-toolkit-notebook:v2.0",
    },
    id="ml_toolkit_v2",
),
```

### 4.2 Update Package List

In the test method, customize the packages to verify:

```python
# Original
packages_to_verify = ["sdg_hub", "instructlab"]

# Your packages
packages_to_verify = ["numpy", "pandas", "scikit-learn", "tensorflow"]
```

**Tip**: List only the key packages that define your image. Don't list standard library packages.

---

## Step 5: Run the Test

### 5.1 Run Single Test

```bash
pytest tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[your_test_id] -v
```

Replace `your_test_id` with the `id` you set in parametrization.

### 5.2 Run All Custom Image Tests

```bash
pytest tests/workbenches/notebook-controller/test_custom_images.py -v
```

### 5.3 Run with Sanity Marker

```bash
pytest -m sanity tests/workbenches/notebook-controller/test_custom_images.py -v
```

---

## Step 6: Interpret Results

### Success Output

```
tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[your_test_id] PASSED [100%]

======================================== 1 passed in 482.35s (0:08:02) ========================================
```

**Expected Duration**: 8-12 minutes (10 min for pod readiness + 1-2 min for verification)

### Failure Output: Package Not Found

```
tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[your_test_id] FAILED

AssertionError: The following packages are not importable in test-your-image:
  - missing_package: ModuleNotFoundError: No module named 'missing_package'
```

**Action**: Contact image team to add missing package to image build.

### Failure Output: Image Pull Error

```
TimeoutExpiredError: Timed out waiting for condition Ready on Pod test-your-image-0

Pod status: Pending
Container status: ImagePullBackOff
Reason: Failed to pull image "quay.io/org/your-image:tag": rpc error: code = Unknown desc = Error reading manifest tag in quay.io/org/your-image: manifest unknown
```

**Actions**:
1. Verify image URL is correct (check registry, org, repo, tag)
2. Verify test cluster has pull access to registry
3. Check if image exists in registry using `podman search` or web UI

### Failure Output: Pod Crash

```
TimeoutExpiredError: Timed out waiting for condition Ready on Pod test-your-image-0

Pod status: CrashLoopBackOff
Container status: Error
Logs:
  /opt/app-root/bin/start-notebook.sh: line 12: jupyter: command not found
```

**Action**: Image is missing Jupyter - contact image team.

---

## Step 7: Document Your Test

Add a comment above your test parametrization explaining:

```python
# Test Case: ML Toolkit Notebook v2.0
# Image: quay.io/myorg/ml-toolkit-notebook:v2.0
# Required Packages: numpy, pandas, scikit-learn, tensorflow
# Purpose: Validate ML toolkit image for data science workflows
# Contact: ml-toolkit-team@example.com
pytest.param(
    {"name": "test-ml-toolkit", "add-dashboard-label": True},
    {"name": "test-ml-toolkit"},
    {
        "namespace": "test-ml-toolkit",
        "name": "test-ml-toolkit",
        "custom_image": "quay.io/myorg/ml-toolkit-notebook:v2.0",
    },
    id="ml_toolkit_v2",
),
```

---

## Advanced Usage

### Multiple Packages for Same Image

```python
packages_to_verify = [
    "numpy",
    "pandas",
    "matplotlib",
    "scikit-learn",
    "tensorflow",
    "torch",
]
```

**Duration Impact**: +1 second per additional package

### Custom Auth Sidecar Resources

If your image requires more resources for the auth sidecar:

```python
pytest.param(
    {"name": "test-gpu-image", "add-dashboard-label": True},
    {"name": "test-gpu-image"},
    {
        "namespace": "test-gpu-image",
        "name": "test-gpu-image",
        "custom_image": "quay.io/org/gpu-notebook:latest",
        "auth_annotations": {
            "notebooks.opendatahub.io/auth-sidecar-cpu-request": "500m",
            "notebooks.opendatahub.io/auth-sidecar-memory-limit": "512Mi",
        },
    },
    id="gpu_image",
),
```

### Parametrize Multiple Images

Test multiple versions of the same image:

```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        pytest.param(
            {"name": f"test-sdg-v{version}", "add-dashboard-label": True},
            {"name": f"test-sdg-v{version}"},
            {
                "namespace": f"test-sdg-v{version}",
                "name": f"test-sdg-v{version}",
                "custom_image": f"quay.io/org/sdg-hub:{version}",
            },
            id=f"sdg_hub_{version}",
        )
        for version in ["2025.1", "2025.2", "latest"]
    ],
    indirect=True,
)
def test_custom_image_package_verification(...):
    # Test runs 3 times, once per version
```

---

## Troubleshooting

### Issue: Test times out during pod readiness

**Symptom**: `TimeoutExpiredError` after 10 minutes

**Common Causes**:
1. **Large image**: Image size > 5GB, increase timeout
2. **Registry throttling**: Too many pulls from same registry
3. **Network issues**: Cluster cannot reach registry

**Solutions**:
- Check image size: `podman inspect quay.io/org/image:tag | grep Size`
- Verify registry access: `oc run test-pull --image=quay.io/org/image:tag --rm -it`
- Check cluster events: `oc get events -n test-namespace`

### Issue: Package import fails but package is in image

**Symptom**: `ModuleNotFoundError` for package that should exist

**Common Causes**:
1. Package installed in wrong Python environment
2. Package name mismatch (pip name vs import name)
3. Missing system dependencies

**Solutions**:
- Verify Python environment: Package in `/opt/app-root/lib/python3.X/site-packages`?
- Check pip vs import name: `pip` installs `pillow`, import is `PIL`
- Test locally: `podman run -it image:tag python -c 'import package'`

### Issue: Permission errors during verification

**Symptom**: `PermissionError` or `OSError` during import

**Common Causes**:
1. Package requires write access (e.g., creating cache files)
2. Home directory not writable
3. Incorrect file permissions in image

**Solutions**:
- Test with read-only import: `python -c 'import package; print(package.__version__)'`
- Check file permissions in image
- Contact image team to fix permissions

---

## Best Practices

### DO
✓ Use versioned image tags (`2025.1` not `latest`)
✓ Test key packages only (3-5 packages max)
✓ Add descriptive test IDs and comments
✓ Coordinate with image team for package lists
✓ Run test locally before committing

### DON'T
✗ Use `latest` tags in production tests (non-reproducible)
✗ Test standard library packages (`import os`, `import sys`)
✗ Skip namespace uniqueness (causes test conflicts)
✗ Hardcode timeouts (use `Timeout` constants)
✗ Ignore test failures (investigate root cause)

---

## Checklist

Before committing your test:

- [ ] Gathered image URL and package list from image team
- [ ] Updated test parametrization with unique namespace/name
- [ ] Customized package list for your image
- [ ] Ran test successfully at least once
- [ ] Test duration < 12 minutes
- [ ] Added descriptive ID and comments
- [ ] Verified backward compatibility (existing tests still pass)
- [ ] Documented image version and contact info

---

## Getting Help

### Common Questions

**Q: How long should the test take?**
A: 8-12 minutes total. 10 minutes for pod readiness + 1-2 minutes for verification.

**Q: Can I test multiple images in one test method?**
A: Yes, use parametrize with multiple `pytest.param()` entries.

**Q: What if my image requires GPU?**
A: Add test to GPU-enabled test cluster. No code changes needed.

**Q: How do I know what packages to test?**
A: Ask the image team for their "key packages" list. Don't test all packages.

### Contact

- **QE Team**: For test framework questions
- **Workbench Image Team**: For image-specific questions
- **Repository**: `opendatahub-tests` on GitHub

---

## Next Steps

After successfully adding your test:

1. ✓ Commit your changes with descriptive message
2. ✓ Open PR for review
3. ✓ Verify CI pipeline runs your test
4. ✓ Coordinate with image team for ongoing updates
5. ✓ Document test in team wiki/runbook

**Congratulations!** You've added a custom image validation test to the suite.
