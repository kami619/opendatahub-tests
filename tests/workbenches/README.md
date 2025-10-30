# Workbenches Tests

This directory contains tests for OpenDataHub/RHOAI Workbenches (Notebooks) functionality.

## Test Structure

- `notebook-controller/` - Tests for notebook controller functionality
  - `test_spawning.py` - Tests for notebook creation and spawning

## Prerequisites

For detailed prerequisites, see the main [Getting Started Guide](../../docs/GETTING_STARTED.md).

### Key Requirements

1. **OpenDataHub/RHOAI Installed**
   - DataScienceCluster (DSC) with workbenches component enabled
   - DSCInitialization (DSCI) configured
   - Notebook controller pods running in applications namespace

2. **Storage**
   - Default storage class available
   - Support for RWO (ReadWriteOnce) PVCs

3. **Workbench Images**
   - For RHOAI (downstream): `s2i-minimal-notebook:2025.2`
   - For ODH (upstream): `jupyter-minimal-notebook:2025.2`
   - Available via internal image registry or external registry

4. **User Configuration** (Optional)
   - For unprivileged client tests: LDAP configured with `openldap` namespace and secret
   - For admin client tests: Use `--tc=use_unprivileged_client:False`

## Running the Tests

### With Admin Client (Recommended for Development)
```bash
uv run pytest tests/workbenches/ --tc=use_unprivileged_client:False
```

### With Unprivileged Client (Default)
```bash
uv run pytest tests/workbenches/
```

### Run Specific Tests
```bash
# Single test
uv run pytest tests/workbenches/notebook-controller/test_spawning.py::TestNotebook::test_create_simple_notebook

# All notebook-controller tests
uv run pytest tests/workbenches/notebook-controller/
```

## Troubleshooting

### Issue: Namespace Stuck in Terminating State

**Symptom:**
```
kubernetes.dynamic.exceptions.ConflictError: 409
HTTP response body: "project.project.openshift.io \"test-odh-notebook\" already exists"
```

**Cause:**
The test namespace from a previous run is stuck in `Terminating` state, usually due to:
- Test interrupted (Ctrl+C)
- Notebook CR with stuck finalizer
- Cleanup timeout exceeded

**Solution:**

1. Check the namespace status:
   ```bash
   oc get project test-odh-notebook
   ```

2. If it shows `Terminating` status, check what's blocking:
   ```bash
   oc get all,notebook,pvc -n test-odh-notebook
   ```

3. If a Notebook CR exists, check its finalizers:
   ```bash
   oc get notebook -n test-odh-notebook
   oc get notebook <notebook-name> -n test-odh-notebook -o jsonpath='{.metadata.finalizers}'
   ```

4. Remove the stuck finalizer:
   ```bash
   oc patch notebook <notebook-name> -n test-odh-notebook \
     -p '{"metadata":{"finalizers":[]}}' --type=merge
   ```

5. The namespace should now delete automatically. Verify:
   ```bash
   oc get project test-odh-notebook
   # Should return: Error from server (NotFound)
   ```

**Common Stuck Finalizers:**
- `notebook.opendatahub.io/kube-rbac-proxy-cleanup` - Most common, handles auth proxy cleanup

**Quick Cleanup Script:**
```bash
#!/bin/bash
# cleanup-stuck-notebook-namespace.sh
NAMESPACE=$1

if [ -z "$NAMESPACE" ]; then
  echo "Usage: $0 <namespace-name>"
  exit 1
fi

echo "Checking namespace: $NAMESPACE"
if ! oc get project "$NAMESPACE" &> /dev/null; then
  echo "Namespace does not exist or is already deleted."
  exit 0
fi

# Check if terminating
STATUS=$(oc get project "$NAMESPACE" -o jsonpath='{.status.phase}')
if [ "$STATUS" != "Terminating" ]; then
  echo "Namespace is not stuck (status: $STATUS). Use 'oc delete project $NAMESPACE' instead."
  exit 0
fi

echo "Namespace is stuck in Terminating state. Removing finalizers from notebooks..."

# Remove finalizers from all notebooks
for notebook in $(oc get notebook -n "$NAMESPACE" -o name 2>/dev/null); do
  echo "Removing finalizers from $notebook"
  oc patch "$notebook" -n "$NAMESPACE" -p '{"metadata":{"finalizers":[]}}' --type=merge
done

echo "Waiting for namespace deletion..."
sleep 5

if oc get project "$NAMESPACE" &> /dev/null; then
  echo "Namespace still exists. Check manually: oc get project $NAMESPACE -o yaml"
else
  echo "Namespace successfully deleted!"
fi
```

### Issue: No Notebook Controller Found

**Symptom:**
Notebooks don't spawn or reconcile.

**Solution:**
Check if notebook controllers are running:
```bash
oc get pods -n redhat-ods-applications | grep notebook
```

Expected output should include:
- `notebook-controller-deployment-*`
- `odh-notebook-controller-manager-*`

If missing, verify workbenches component in DSC:
```bash
oc get dsc default-dsc -o jsonpath='{.spec.components.workbenches.managementState}'
# Should return: Managed
```

### Issue: Image Pull Errors

**Symptom:**
Notebook pod fails with `ImagePullBackOff` or `ErrImagePull`.

**Solution:**
1. Check if imagestream exists:
   ```bash
   oc get imagestream s2i-minimal-notebook -n redhat-ods-applications
   ```

2. Check if specific tag exists:
   ```bash
   oc get imagestream s2i-minimal-notebook -n redhat-ods-applications \
     -o jsonpath='{.spec.tags[?(@.name=="2025.2")].name}'
   ```

3. Verify internal image registry is running:
   ```bash
   oc get service -n openshift-image-registry image-registry
   ```

### Issue: PVC Provisioning Fails

**Symptom:**
PVC stuck in `Pending` state.

**Solution:**
1. Check storage class availability:
   ```bash
   oc get storageclass
   ```

2. Describe the PVC to see events:
   ```bash
   oc describe pvc <pvc-name> -n test-odh-notebook
   ```

3. Ensure default storage class is set:
   ```bash
   oc get storageclass -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}'
   ```

### Issue: LDAP Authentication Fails (Unprivileged Client)

**Symptom:**
```
ValueError: Unprivileged user not provisioned
```

**Solution:**
Either configure LDAP or use admin client:

1. **Option 1 - Use Admin Client:**
   ```bash
   pytest tests/workbenches/ --tc=use_unprivileged_client:False
   ```

2. **Option 2 - Verify LDAP Configuration:**
   ```bash
   # Check LDAP namespace exists
   oc get namespace openldap
   
   # Check LDAP secret exists
   oc get secret openldap -n openldap
   
   # Verify users are configured
   oc get secret openldap -n openldap -o jsonpath='{.data.users}' | base64 -d
   ```

### Issue: Notebook Pod Not Ready

**Symptom:**
Pod exists but never reaches `Ready` state, test times out.

**Solution:**
1. Check pod status:
   ```bash
   oc get pods -n test-odh-notebook
   ```

2. Check pod events:
   ```bash
   oc describe pod test-odh-notebook-0 -n test-odh-notebook
   ```

3. Check container logs:
   ```bash
   # Main notebook container
   oc logs test-odh-notebook-0 -n test-odh-notebook -c test-odh-notebook
   
   # Auth proxy container
   oc logs test-odh-notebook-0 -n test-odh-notebook -c kube-rbac-proxy
   ```

4. Common issues:
   - Missing ConfigMap: `test-kube-rbac-proxy-config`
   - Missing Secret: `test-kube-rbac-proxy-tls`
   - Missing ServiceAccount

## Fixture Architecture

The workbench tests use a hierarchical fixture structure to provision test resources. Key fixtures are defined in `conftest.py`:

### Core Fixtures (in order of dependency)

1. **`unprivileged_model_namespace`** - Creates a test namespace
2. **`users_persistent_volume_claim`** - Creates a PVC for notebook storage
3. **`notebook_service_account`** - Creates a ServiceAccount for the notebook pod
4. **`notebook_rbac_config_map`** - Creates a ConfigMap with kube-rbac-proxy authorization rules
5. **`notebook_rbac_tls_secret`** - Creates a Secret with TLS certificates for kube-rbac-proxy
6. **`default_notebook`** - Creates the Notebook CR with all required resources

### Fixture Dependencies

```
default_notebook
├── notebook_service_account
├── notebook_rbac_config_map
│   └── notebook_rbac_tls_secret
└── unprivileged_model_namespace
    └── users_persistent_volume_claim
```

### Notable Implementation Details

- **Kube-RBAC-Proxy Sidecar**: The notebook pod includes a kube-rbac-proxy sidecar container for RBAC enforcement
  - Requires ServiceAccount with proper RBAC roles (handled by notebook-controller)
  - Requires ConfigMap (`test-kube-rbac-proxy-config`) with authorization rules
  - Requires Secret (`test-kube-rbac-proxy-tls`) with TLS certificate/key pair

- **Finalizer Cleanup**: The `default_notebook` fixture removes the `notebook.opendatahub.io/kube-rbac-proxy-cleanup` finalizer during teardown to prevent namespace deletion issues
  - See: [Issue: Namespace Stuck in Terminating State](#issue-namespace-stuck-in-terminating-state)

- **TLS Certificate**: Uses a valid self-signed certificate (base64-encoded)
  - Generated with: `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=test"`

## Additional Resources

- [Developer Guide](../../docs/DEVELOPER_GUIDE.md)
- [Getting Started Guide](../../docs/GETTING_STARTED.md)
- [Style Guide](../../docs/STYLE_GUIDE.md)

## Contributing

When adding new workbench tests:
1. Follow the existing test structure
2. Use fixtures from `conftest.py` for resource creation
3. Add appropriate markers (e.g., `@pytest.mark.smoke`)
4. Update this README if adding new test categories or prerequisites

