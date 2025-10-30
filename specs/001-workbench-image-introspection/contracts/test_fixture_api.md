# API Contract: Custom Image Test Fixture

**Module**: `tests.workbenches.conftest`
**Fixture**: `default_notebook` (enhanced)
**Version**: 1.0.0
**Date**: 2025-10-30

---

## Fixture Signature

```python
@pytest.fixture(scope="function")
def default_notebook(
    request: pytest.FixtureRequest,
    admin_client: DynamicClient,
    minimal_image: str,
) -> Generator[Notebook, None, None]:
    """
    Returns a new Notebook CR for a given namespace, name, and image.

    Supports both default minimal images and custom workbench images via parametrization.

    Yields:
        Notebook: A Notebook custom resource instance managed by context manager.
                  Automatically cleaned up after test completion.

    Parametrization:
        Required parameters (via request.param dict):
        - namespace (str): Kubernetes namespace for notebook
        - name (str): Name of the notebook resource

        Optional parameters:
        - custom_image (str): Full custom image URL. If provided, overrides minimal_image.
                             Must include registry, repository, and tag.
                             Example: "quay.io/opendatahub/sdg-hub-notebook:2025.1"
        - auth_annotations (dict[str, str]): Auth sidecar resource annotations
                                             Example: {
                                                 "notebooks.opendatahub.io/auth-sidecar-cpu-request": "200m"
                                             }

    Example Usage:
        @pytest.mark.parametrize(
            "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
            [
                pytest.param(
                    {"name": "test-custom", "add-dashboard-label": True},
                    {"name": "test-custom"},
                    {
                        "namespace": "test-custom",
                        "name": "test-custom",
                        "custom_image": "quay.io/org/custom:latest",
                    },
                    id="custom_image_test",
                )
            ],
            indirect=True,
        )
        def test_custom_image(self, default_notebook: Notebook):
            # Test receives a Notebook with custom image
            pass
    """
```

---

## Input Contract

### Required Parameters

| Parameter | Type | Validation | Error if Missing |
|-----------|------|------------|------------------|
| `namespace` | `str` | Non-empty, valid k8s namespace name | `KeyError("namespace")` |
| `name` | `str` | Non-empty, valid k8s resource name | `KeyError("name")` |

### Optional Parameters

| Parameter | Type | Default | Validation |
|-----------|------|---------|------------|
| `custom_image` | `str | None` | `None` | Must be full image URL with tag if provided |
| `auth_annotations` | `dict[str, str]` | `{}` | Dict of string key-value pairs |

### Parameter Validation Rules

**namespace**:
- Pattern: `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`
- Max length: 63 characters
- Namespace must exist or be created by `unprivileged_model_namespace` fixture

**name**:
- Pattern: `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`
- Max length: 63 characters
- Must be unique within namespace

**custom_image**:
- Pattern: `^[a-z0-9.-]+/[a-z0-9._-]+/[a-z0-9._-]+:[a-z0-9._-]+$`
- Must include: `registry/org/repo:tag`
- Examples:
  - Valid: `quay.io/opendatahub/workbench:2025.1`
  - Valid: `registry.redhat.io/rhoai/notebook-py311:latest`
  - Invalid: `workbench:latest` (missing registry)
  - Invalid: `quay.io/workbench` (missing tag)

---

## Image Resolution Logic

### Decision Flow

```
START
  ↓
custom_image parameter provided?
  ├─ YES → Use custom_image directly
  │         (Assume full registry path)
  │         ↓
  │       minimal_image_path = custom_image
  │
  └─ NO  → Use minimal_image from fixture
            ↓
          Internal registry available?
            ├─ YES → Prepend internal registry path
            │        minimal_image_path = f"{INTERNAL_IMAGE_REGISTRY_PATH}/{namespace}/{minimal_image}"
            │
            └─ NO  → Use tag-only format
                     minimal_image_path = f":{minimal_image.split(':')[1]}"
END
```

### Code Implementation

```python
# Extract parameters
namespace = request.param["namespace"]
name = request.param["name"]
auth_annotations = request.param.get("auth_annotations", {})
custom_image = request.param.get("custom_image", None)

# Determine which image to use
if custom_image:
    # Custom image provided - use as-is
    minimal_image_path = custom_image
else:
    # Default minimal image - apply registry logic
    internal_image_registry = check_internal_image_registry_available(admin_client=admin_client)
    minimal_image_path = (
        f"{INTERNAL_IMAGE_REGISTRY_PATH}/{py_config['applications_namespace']}/{minimal_image}"
        if internal_image_registry
        else ":" + minimal_image.rsplit(":", maxsplit=1)[1]
    )
```

---

## Output Contract

### Notebook Resource Attributes

The yielded `Notebook` object has the following key attributes:

```python
notebook.name: str           # Notebook CR name (matches input parameter)
notebook.namespace: str      # Namespace (matches input parameter)
notebook.exists: bool        # Always True when yielded
notebook.instance: dict      # Full Notebook CR as dict

# Key instance fields
notebook.instance.spec.template.spec.containers[0].image: str  # Resolved image path
notebook.instance.metadata.annotations: dict                    # Includes auth_annotations
notebook.instance.metadata.labels: dict                         # Dashboard labels

# Pod information (derived)
pod_name: str = f"{notebook.name}-0"  # Generated by notebook controller
container_name: str = notebook.name   # Main container matches notebook name
```

### Guaranteed State

When fixture yields, the Notebook:
1. ✓ Exists in Kubernetes API
2. ✓ Has all required labels (`opendatahub.io/dashboard: "true"`)
3. ✓ Has correct image configured in spec
4. ✓ Has authentication sidecar configured
5. ✗ Pod may not yet exist (test must wait for pod)
6. ✗ Pod may not yet be ready (test must wait for ready state)

**Important**: Tests must explicitly wait for pod readiness:
```python
notebook_pod = Pod(
    client=unprivileged_client,
    namespace=default_notebook.namespace,
    name=f"{default_notebook.name}-0",
)
notebook_pod.wait()
notebook_pod.wait_for_condition(
    condition=Pod.Condition.READY,
    status=Pod.Condition.Status.TRUE
)
```

---

## Cleanup Contract

### Automatic Cleanup

The fixture uses a context manager (`with Notebook(...) as nb`), which guarantees:

1. **On test success**: Notebook CR deleted
2. **On test failure**: Notebook CR deleted
3. **On test error**: Notebook CR deleted
4. **Deletion propagation**: Kubernetes garbage collection deletes associated resources:
   - Pod: `{notebook-name}-0`
   - ServiceAccount: `{notebook-name}`
   - RoleBinding: `{notebook-name}-*`
   - ConfigMap: `test-kube-rbac-proxy-config` (shared)
   - Secret: `test-kube-rbac-proxy-tls` (shared)

### Cleanup Timing

- Deletion initiated: Immediately after test completes
- Pod termination: Up to 30 seconds (graceful shutdown)
- Full cleanup: Up to 60 seconds (including PVC if created)

---

## Backward Compatibility

### Existing Tests Unaffected

**Scenario**: Test using default minimal image (no custom_image parameter)

**Before enhancement**:
```python
pytest.param(
    {"name": "test-ns", "add-dashboard-label": True},
    {"name": "test-pvc"},
    {
        "namespace": "test-ns",
        "name": "test-notebook",
    },
)
```

**After enhancement**: Same parameters work identically
- `custom_image` defaults to `None`
- Existing image resolution logic unchanged
- No changes required to existing tests

---

## Error Handling Contract

### Fixture-Level Errors

| Error Condition | Exception | When Raised |
|----------------|-----------|-------------|
| Missing namespace parameter | `KeyError("namespace")` | Fixture setup |
| Missing name parameter | `KeyError("name")` | Fixture setup |
| Invalid custom_image format | `AssertionError` | Fixture setup (validation) |
| Notebook creation fails | `K8sApiException` | Fixture setup |
| Username lookup fails | `AssertionError` | Fixture setup |

### Test-Level Errors

These errors occur during test execution (after fixture yields):

| Error Condition | Exception | Handling |
|----------------|-----------|----------|
| Pod not created | `ResourceNotFoundError` | Test waits with timeout |
| Image pull fails | `TimeoutExpiredError` | Test checks pod status |
| Pod crashes | `TimeoutExpiredError` | Test checks container status |

---

## Integration with Other Fixtures

### Fixture Dependency Chain

```
admin_client (session scope)
    ↓
minimal_image (function scope)
    ↓
default_notebook (function scope)
    ├─ requires: unprivileged_model_namespace (indirect param)
    └─ requires: users_persistent_volume_claim (indirect param)
```

### Parametrization Coordination

All three fixtures must be parametrized together:

```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        pytest.param(
            # Parameter dict for unprivileged_model_namespace
            {"name": "test-ns", "add-dashboard-label": True},
            # Parameter dict for users_persistent_volume_claim
            {"name": "test-pvc"},
            # Parameter dict for default_notebook
            {"namespace": "test-ns", "name": "test-nb", "custom_image": "..."},
        )
    ],
    indirect=True,
)
```

---

## Container Configuration

### Main Notebook Container

```python
{
    "name": name,  # Matches notebook name
    "image": minimal_image_path,  # Resolved image
    "imagePullPolicy": "Always",
    "env": [
        {"name": "NOTEBOOK_ARGS", "value": "--ServerApp.port=8888 ..."},
        {"name": "JUPYTER_IMAGE", "value": minimal_image_path},
    ],
    "ports": [{"containerPort": 8888, "name": "notebook-port", "protocol": "TCP"}],
    "resources": {
        "limits": {"cpu": "2", "memory": "4Gi"},
        "requests": {"cpu": "1", "memory": "1Gi"},
    },
    "volumeMounts": [
        {"mountPath": "/opt/app-root/src", "name": name},
        {"mountPath": "/dev/shm", "name": "shm"},
    ],
    "workingDir": "/opt/app-root/src",
}
```

### Auth Sidecar Container

```python
{
    "name": "kube-rbac-proxy",
    "image": "quay.io/rhoai/odh-kube-auth-proxy-rhel9:rhoai-3.0",
    "ports": [{"containerPort": 8443, "name": "kube-rbac-proxy", "protocol": "TCP"}],
    "resources": {
        "limits": {"cpu": "100m", "memory": "64Mi"},
        "requests": {"cpu": "100m", "memory": "64Mi"},
    },
    # Can be customized via auth_annotations parameter
}
```

---

## Performance Contract

### Resource Usage

| Resource | Default | Custom Image Impact |
|----------|---------|---------------------|
| CPU request | 1 core | No change |
| CPU limit | 2 cores | No change |
| Memory request | 1Gi | No change |
| Memory limit | 4Gi | No change |
| Image pull time | ~30s (minimal) | Up to 10min (large custom) |
| Pod startup time | ~20s | ~30s (custom image) |

### Fixture Timing

- Setup time: 5-10 seconds (create Notebook CR)
- Teardown time: 10-20 seconds (delete resources)
- Total overhead: 15-30 seconds per test

---

## Security Contract

### RBAC Configuration

**Service Account**: Created per notebook, named `{notebook-name}`

**Permissions**: Configured via RoleBinding
- View own namespace
- Access own PVC
- Query own routes

**Authentication**: OAuth proxy sidecar enforces authentication
- Configured via annotations
- Customizable resources via `auth_annotations` parameter

### Image Pull Secrets

- Default: Cluster-level pull secrets used
- Custom images: Must be accessible with cluster credentials
- No additional image pull secrets configured by fixture

---

## Observability

### Logging

Fixture logs at INFO level:
- Notebook creation: `Creating notebook {name} in {namespace}`
- Image selection: `Using custom image: {custom_image}` or `Using minimal image: {minimal_image}`
- Username lookup: `Determined username: {username}`
- Cleanup: `Cleaning up notebook {name}`

### Debugging

For troubleshooting, access notebook details:
```python
def test_debug(self, default_notebook: Notebook):
    print(f"Notebook name: {default_notebook.name}")
    print(f"Notebook namespace: {default_notebook.namespace}")
    print(f"Full spec: {default_notebook.instance.to_str()}")
```

---

## Example Usage Patterns

### Pattern 1: Default Minimal Image (Existing Behavior)

```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        pytest.param(
            {"name": "test-default", "add-dashboard-label": True},
            {"name": "test-default"},
            {"namespace": "test-default", "name": "test-default"},
            id="default_minimal",
        )
    ],
    indirect=True,
)
def test_with_default_image(self, default_notebook: Notebook):
    # Uses minimal_image fixture (upstream or s2i)
    assert default_notebook.exists
```

### Pattern 2: Custom Image

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
                "custom_image": "quay.io/opendatahub/sdg-hub:2025.1",
            },
            id="custom_sdg_hub",
        )
    ],
    indirect=True,
)
def test_with_custom_image(self, default_notebook: Notebook):
    # Uses specified custom image
    assert "sdg-hub" in default_notebook.instance.spec.template.spec.containers[0].image
```

### Pattern 3: Custom Image + Auth Annotations

```python
@pytest.mark.parametrize(
    "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
    [
        pytest.param(
            {"name": "test-both", "add-dashboard-label": True},
            {"name": "test-both"},
            {
                "namespace": "test-both",
                "name": "test-both",
                "custom_image": "quay.io/opendatahub/gpu-notebook:latest",
                "auth_annotations": {
                    "notebooks.opendatahub.io/auth-sidecar-cpu-request": "500m",
                    "notebooks.opendatahub.io/auth-sidecar-memory-limit": "512Mi",
                },
            },
            id="gpu_with_auth",
        )
    ],
    indirect=True,
)
def test_with_custom_image_and_auth(self, default_notebook: Notebook):
    # Custom image + custom auth resources
    assert default_notebook.exists
```

---

## Change Log

### Version 1.0.0 (2025-10-30)
- Added `custom_image` optional parameter
- Maintains 100% backward compatibility
- Enhanced image resolution logic
- Updated documentation
