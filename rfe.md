# Re-factor workbenches tests in opendatahub-tests repo

**Feature Overview:**

The current workbench spawning test provides minimal value, only confirming that a pod can be created. This RFE proposes enhancing our test framework to support spawning **custom** workbench images and, crucially, adding introspection capabilities to verify software and packages (like `sdg_hub`) installed *within* the running workbench. By extending the test infrastructure to execute commands inside workbench pods and verify package availability, we can catch image-build errors, missing dependencies, and configuration issues before they reach users. This enhancement transforms workbench tests from simple pod creation smoke tests into comprehensive image validation tests that provide real confidence in the functionality of custom workbench images.

---

**Goals:**

* Improve the reliability and coverage of our workbench testing suite by moving beyond simple pod spawning to actual in-pod validation
* Provide a reusable test utility that allows developers to easily test custom workbench images and verify their contents using pod execution capabilities
* Enable automated testing of workbench images that depend on specific packages, starting with `sdg_hub`, to catch image-build or dependency errors early in the development cycle
* Establish clear patterns for image validation that can scale to additional custom images (e.g., instructlab, GPU-enabled, Elyra pipelines)
* Create documentation that clearly defines ownership boundaries between test code maintenance (QE team) and custom image builds (workbench image teams)

---

**Out of Scope:**

* Refactoring any other test suites (e.g., model serving, model registry, or other non-workbench related tests)
* Testing the full functionality of the `sdg_hub` example notebook by executing notebook cells (e.g., running a full "knowledge_tuning" job). The MVP test focuses on package presence and importability only
* Building the custom workbench images themselves (this RFE covers *testing* them, not building them)
* Executing instructlab example notebooks end-to-end (deferred to future enhancement)
* Creating new directory structures (`tests/workbenches/images/`) - tests will remain in `notebook-controller/` directory
* Generic script execution framework for running arbitrary code in workbenches (MVP focuses on package import verification)

---

**Requirements:**

1.  **(MVP)** Extend the existing `default_notebook` fixture in `tests/workbenches/conftest.py` to accept a `custom_image` parameter, allowing tests to specify custom workbench image URLs
2.  **(MVP)** Create a new test utility function `verify_package_in_workbench()` in `tests/workbenches/utils.py` that uses `ocp_resources` Pod.execute() to run commands inside workbench containers
3.  **(MVP)** The new utility must verify that specified Python packages (starting with `sdg_hub`) are successfully installed and importable *inside* the spawned workbench environment using `python -c "import <package>"` commands
4.  **(MVP)** Create a new test file `tests/workbenches/notebook-controller/test_custom_images.py` with a test case that spawns a custom workbench image and verifies `sdg_hub` package availability
5.  **(MVP)** Implement proper timeout handling with `TIMEOUT_10MIN` for pod readiness (to accommodate large custom image pulls) and `TIMEOUT_1MIN` for command execution
6.  **(MVP)** Add comprehensive error handling that captures pod logs on failure and provides actionable error messages for debugging
7.  The new test must use `@pytest.mark.sanity` and `@pytest.mark.slow` markers (not smoke, due to extended runtime)
8.  The existing `test_spawning.py` tests should remain unchanged and continue to pass
9.  Create `tests/workbenches/README.md` documenting the test structure, ownership model, and how to add new custom image tests
10. Coordinate with workbench image team to identify the location of the `sdg_hub`-enabled workbench image (blocker for implementation) or fall back on using the existing minimal image defined in the notebook fixture for the initial validation.

---

**Done - Acceptance Criteria:**

* The `default_notebook` fixture in `tests/workbenches/conftest.py` accepts an optional `custom_image` parameter in its parametrization
* A new utility function `verify_package_in_workbench(pod, package_name, container_name, timeout)` exists in `tests/workbenches/utils.py` with comprehensive docstrings
* A new test file `tests/workbenches/notebook-controller/test_custom_images.py` exists with at least one test case
* This new test case successfully spawns a workbench using a custom image URL (e.g., one containing `sdg_hub`) with a 10-minute timeout for image pull and pod readiness
* The test case *executes code inside the workbench* using `pod.execute()` method from `ocp_resources` library (specifically `python -c "import sdg_hub; print('SUCCESS')"`) and asserts successful completion
* The test case fails gracefully with clear error messages and pod logs if the package is *not* found or if pod never reaches Running state
* The existing `test_spawning.py` tests (test_create_simple_notebook, test_auth_container_resource_customization) continue to pass without modification
* A `tests/workbenches/README.md` file exists documenting test structure, ownership, supported custom images, and onboarding process for adding new tests
* The test is marked with `@pytest.mark.sanity` and `@pytest.mark.slow` (appropriately categorized for CI runtime)
* Documentation includes configuration placeholder for custom image location pending coordination with image build team

---

**Use Cases - i.e. User Experience & Workflow:**

### Main Success Scenario: QE Developer Tests Custom Workbench Image

1.  **Developer Workflow:** A developer on the workbench image team builds a new custom workbench image (e.g., `quay.io/opendatahub/instructlab-workbench:2025.2`) that includes the `sdg_hub` package for instructlab integration
2.  **Test Configuration:** QE team adds the image configuration to test parametrization in `test_custom_images.py`:
    ```python
    pytest.param(
        {"name": "test-sdg-workbench", "add-dashboard-label": True},
        {"name": "test-sdg-workbench"},
        {
            "namespace": "test-sdg-workbench",
            "name": "test-sdg-workbench",
            "custom_image": "quay.io/opendatahub/instructlab-workbench:2025.2",
        },
    )
    ```
3.  **Test Execution:** The developer (or CI) runs: `pytest tests/workbenches/notebook-controller/test_custom_images.py -v`
4.  **Test Action - Spawning:** The test framework calls the extended `default_notebook` fixture with the custom image URL, creating a Notebook CR with the specified image
5.  **Test Action - Waiting:** Test waits up to 10 minutes for the workbench pod to reach Running state (accommodating potentially large custom image pull from registry)
6.  **Test Action - Verification:** Test calls `verify_package_in_workbench()` which executes `python -c "import sdg_hub; print('SUCCESS')"` inside the notebook container using `pod.execute()`
7.  **Outcome - Success:** The test passes because the import command returns exit code 0 and output contains "SUCCESS"
8.  **Outcome - Failure:** If the package was missing, the command would raise `ExecOnPodError`, pod logs would be captured, and the test would be marked as `Failed` with clear diagnostic message

### Alternative Flow 1: Image Pull Failure

**Trigger:** Custom image URL is incorrect or inaccessible from test cluster

**Flow:**
1. Test creates Notebook CR with custom image
2. Pod enters ImagePullBackOff state
3. `wait_for_condition(Pod.Condition.READY, timeout=TIMEOUT_10MIN)` times out after 10 minutes
4. Test captures pod events and status
5. Test fails with error message: "Pod never reached Running state. Current phase: Pending. Check image URL and registry access."
6. Developer checks image URL and registry permissions

### Alternative Flow 2: Package Import Failure

**Trigger:** Custom image was built incorrectly and doesn't contain `sdg_hub` package

**Flow:**
1. Test successfully spawns workbench and pod reaches Running state
2. Test executes `python -c "import sdg_hub"`
3. Command raises `ModuleNotFoundError` inside pod
4. `pod.execute()` raises `ExecOnPodError` with stderr containing import error
5. Test enhancement attempts `pip list` to capture installed packages for debugging
6. Test fails with error message: "Failed to import sdg_hub: ModuleNotFoundError: No module named 'sdg_hub'. Check that the custom image includes this package."
7. Developer reviews image build process and Dockerfile

### Alternative Flow 3: Adding a New Custom Image Test

**Trigger:** New GPU-enabled workbench image needs validation

**Actor:** QE Developer

**Flow:**
1. Developer reviews `tests/workbenches/README.md` for onboarding guidance
2. Developer adds new test case to `test_custom_images.py`:
   ```python
   @pytest.mark.parametrize(
       "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
       [
           pytest.param(
               {"name": "test-gpu-workbench", "add-dashboard-label": True},
               {"name": "test-gpu-workbench"},
               {
                   "namespace": "test-gpu-workbench",
                   "name": "test-gpu-workbench",
                   "custom_image": "quay.io/opendatahub/gpu-workbench:2025.2",
               },
           )
       ],
       indirect=True,
   )
   def test_gpu_workbench_packages(self, ...):
       # Reuse existing pattern
       verify_package_in_workbench(pod, "tensorflow", container_name)
       verify_package_in_workbench(pod, "torch", container_name)
   ```
3. Developer runs test locally to verify
4. Test passes, PR is submitted
5. No fixture modifications needed - fully reusable pattern

---

**Documentation Considerations:**

### New Documentation to Create

1. **`tests/workbenches/README.md`** (primary documentation)

   Following the pattern from `tests/llama_stack/README.md`, include:

   - **Directory Structure** - Explanation of `notebook-controller/` contents and purpose
   - **Test Markers** - `@pytest.mark.smoke` for basic spawning, `@pytest.mark.sanity` and `@pytest.mark.slow` for custom images
   - **Custom Image Testing** - Overview of image validation approach
   - **Supported Custom Images** - Table with image names, required packages, and test files
   - **Adding New Custom Image Tests** - Step-by-step guide with code examples
   - **Test Ownership** - Clear boundaries:
     - Test Code: QE/Test Engineering team
     - Custom Images: ODH/RHOAI Workbench image team
     - Test Requests: Process for requesting new test coverage
   - **Troubleshooting** - Common failure scenarios and debugging steps

2. **`tests/workbenches/utils.py`** - Enhanced inline documentation

   Add comprehensive docstring for `verify_package_in_workbench()`:
   ```python
   def verify_package_in_workbench(
       pod: Pod,
       package_name: str,
       container_name: str,
       timeout: int = Timeout.TIMEOUT_1MIN,
   ) -> dict[str, str]:
       """
       Verify that a Python package is installed and importable in a workbench pod.

       This utility executes a Python import statement inside the specified container
       and validates that the package can be successfully imported. This is the primary
       method for validating custom workbench images contain required dependencies.

       Args:
           pod: The workbench Pod instance to inspect
           package_name: Name of the Python package to verify (e.g., "sdg_hub")
           container_name: Name of the container to execute in (typically notebook name)
           timeout: Command execution timeout in seconds (default: 60s)

       Returns:
           dict with 'status' and 'output' keys on success

       Raises:
           AssertionError: If package import fails or pod is not Running

       Example:
           >>> notebook_pod = Pod(client=client, namespace="test", name="notebook-0")
           >>> verify_package_in_workbench(notebook_pod, "sdg_hub", "test-notebook")
           {'status': 'success', 'output': 'SUCCESS'}
       """
   ```

3. **`tests/workbenches/conftest.py`** - Document custom_image parameter

   Update `default_notebook` fixture docstring:
   ```python
   @pytest.fixture(scope="function")
   def default_notebook(...):
       """
       Returns a new Notebook CR for a given namespace, name, and image.

       Supports custom image override via request.param["custom_image"]. If not
       specified, uses the minimal_image fixture (standard test image).

       Parameters (via request.param):
           namespace: Notebook namespace
           name: Notebook name
           custom_image: (Optional) Custom workbench image URL to use instead of minimal_image
           auth_annotations: (Optional) Custom auth sidecar configuration
       """
   ```

### Documentation Updates Needed

- **`docs/DEVELOPER_GUIDE.md`** (if exists) - Add section on workbench test patterns
- **`docs/CONTRIBUTING.md`** - Update test writing guidelines to reference workbench image validation patterns

### Documentation Standards

- All utility functions must have Google-style docstrings with Args, Returns, Raises, and Example sections
- Code examples in documentation must be tested (verified to work)
- Use type hints for all function signatures (already established in existing code)
- Link documentation to reference implementations (e.g., model serving's pod execution pattern in `test_kserve_pvc_write_access.py`)

---

**Questions to answer:**

### Technical Questions (Stella Staff Engineer)

1.  **[ANSWERED - Stella]** What is the preferred mechanism for "verifying" the package? Is a simple `pip show sdg_hub` or `python -c "import sdg_hub"` sufficient for the MVP?

    **Answer:** Use `python -c "import sdg_hub; print('SUCCESS')"` for MVP. Import verification validates actual usability (not just package metadata). Production version can add version checking. Rationale: pip show only validates metadata; imports can fail due to missing C extensions or system libraries even when pip shows the package.

2.  **[ANSWERED - Stella]** How should the test utility get credentials to the pod? Should we rely on the test service account having `exec` permissions, or is there a different introspection method we prefer?

    **Answer:** Use `ocp_resources` Pod.execute() method (Option C). This is the established pattern in the repo (see `test_kserve_pvc_write_access.py:52-55`). The `unprivileged_client` already has sufficient exec permissions. No additional RBAC configuration needed.

3.  **[ANSWERED - Stella]** How should timeouts be handled? Spawning a custom image and running a command will take significantly longer than the current "spawn" test. What are acceptable time limits?

    **Answer:** Use separate timeouts for each phase:
    - Image pull + Pod ready: `TIMEOUT_10MIN` (via `wait_for_condition`)
    - Command execution: `TIMEOUT_1MIN` (via `execute()` parameter)
    - Rationale: Custom images can be multi-GB; 10 minutes accommodates registry throttling and slow pulls

4.  **[ANSWERED - Stella]** The current test uses `minimal_image()`. Should the new utility *replace* this, or should we have two distinct test cases: one for "minimal spawn" and one for "custom image introspection"?

    **Answer:** Keep distinct test cases in separate files:
    - `test_spawning.py` - Existing tests for basic notebook controller mechanics (unchanged)
    - `test_custom_images.py` - New tests for custom image validation
    - Rationale: Clear separation of concerns, different test markers, easier maintenance

### Team Coordination Questions (Lee Team Lead)

5.  **[ANSWERED - Lee]** Do we have a pre-built custom image with `sdg_hub` available for this test to use? Or is the first step to create one and host it in a registry the test cluster can access?

    **Answer:** **BLOCKER** - Custom image location is unknown. Required coordination:
    - Identify workbench image team contact
    - Get image URL (expected: `quay.io/opendatahub/...` or `quay.io/rhoai/...`)
    - Verify test clusters have pull access
    - Establish image versioning strategy (pinned tags vs latest)
    - Document image maintenance ownership

    **Action:** Sync with workbench/instructlab team to identify image location before implementation

6.  **[ANSWERED - Lee]** The note mentions splitting directories. What is the *exact* new directory structure we want? (e.g., `tests/workbenches/notebook-controller/` and `tests/workbenches/workbench-images/`?)

    **Answer:** Keep current structure - DO NOT split directories:
    ```
    tests/workbenches/
    ├── conftest.py
    ├── utils.py
    └── notebook-controller/
        ├── test_spawning.py (existing)
        └── test_custom_images.py (NEW)
    ```
    Rationale: Custom image validation is still testing notebook controller functionality. Other test suites use feature-based subdirectories under common areas. Splitting would fragment a small test suite.

7.  **[ANSWERED - Lee]** Is the `sdg_hub` check the *only* verification we need, or is this a proof-of-concept for a more generic "run-script-in-workbench" test utility?

    **Answer:** MVP focuses on `sdg_hub` import check only. Design utility to be reusable (accepts package name as parameter). Defer generic script execution and notebook cell execution to future enhancements. Rationale: Import check validates primary goal (package presence); full notebook execution has separate complexity.

8.  **[ANSWERED - Lee]** How important is testing the *specific* `instructlab` example notebook mentioned? Or is just checking for the package import enough for the MVP?

    **Answer:** Package import is sufficient for MVP. Notebook execution is a future enhancement requiring:
    - Jupyter kernel API interaction
    - Cell-by-cell execution sequencing
    - Output validation per cell
    - Significantly longer test runtime

    Document as follow-up story: "Add instructlab example notebook execution test"

### Additional Questions Requiring Resolution

9.  **[OPEN]** What is the exact image URL for the `sdg_hub`-enabled workbench image?

    **Status:** Needs coordination with workbench image team. Expected format: `quay.io/opendatahub/workbench-images:instructlab-2025.2` or similar.

    **Blocker:** Implementation cannot proceed without this information.

10. **[OPEN]** Should the custom image test be marked with `@pytest.mark.smoke`?

    **Answer:** NO - use `@pytest.mark.sanity` and `@pytest.mark.slow`. Rationale from Lee:
    - Smoke tests should be fast and stable (core functionality)
    - Custom image pulls add 10-minute runtime and external registry dependency
    - Potential for flakiness (registry throttling, network issues)
    - Run in sanity suite or on merge to main, not every PR

---

**Background & Strategic Fit:**

### Context

The opendatahub-tests repository contains test automation for Open Data Hub (ODH) and Red Hat OpenShift AI (RHOAI). The workbenches component tests verify that Jupyter notebook environments can be created and configured correctly in OpenShift clusters. The Notebook controller is responsible for creating pods from Notebook custom resources, injecting authentication sidecars, managing persistent volumes, and handling resource requests and probes.

Currently, the workbench test suite contains only 2 tests in `tests/workbenches/notebook-controller/test_spawning.py`:
- `test_create_simple_notebook` - Verifies basic notebook spawning with minimal image
- `test_auth_container_resource_customization` - Verifies custom kube-rbac-proxy resource configuration

These tests validate that the notebook controller can create pods, but provide no insight into whether the workbench is **functionally usable** for actual data science work. As OpenShift AI expands to support specialized workbench images (instructlab integration, GPU-enabled environments, custom package sets), we need a testing strategy that verifies image contents and functionality.

### The Problem

**Current State:**
- Workbench tests only verify pod creation (smoke test level)
- No validation that custom images contain required packages
- Image build errors and missing dependencies are only discovered by end users
- Manual testing required for each new custom workbench image
- No established pattern for image validation in the test suite

**Example Failure Scenario:**
1. Workbench image team builds instructlab workbench with `sdg_hub` package
2. Image build succeeds but package has missing dependencies
3. Notebook controller successfully spawns pod (test passes)
4. User opens workbench and tries `import sdg_hub` → fails
5. Issue discovered in production, not in CI

### Strategic Fit

This enhancement aligns with several strategic initiatives:

1. **Instructlab Integration** - As OpenShift AI integrates with instructlab for AI model tuning workflows, we need automated validation that instructlab-enabled workbench images are correctly configured

2. **Custom Workbench Image Support** - Product roadmap includes expanding workbench image catalog (GPU-enabled, domain-specific packages). This testing pattern enables scalable validation

3. **Test Coverage Expansion** - Model serving team has 50+ tests with robust validation. Workbenches is under-tested relative to its importance in the user experience

4. **Shift-Left Testing** - Catching image build errors in CI (before user-facing deployment) reduces support burden and improves product quality

5. **Pattern Consistency** - Model serving tests already use pod execution for validation (see `test_kserve_pvc_write_access.py`). Adopting the same pattern for workbenches improves consistency

### Related Patterns in the Repository

**Established pod execution pattern:**
- Location: `tests/model_serving/model_server/storage/pvc/test_kserve_pvc_write_access.py`
- Pattern: Uses `pod.execute()` from `ocp_resources` library to run commands in containers
- Success: Proven approach for validating container contents and functionality
- Adoption: This RFE applies the same pattern to workbench validation

**Image validation elsewhere:**
- Location: `tests/model_registry/image_validation/`
- Pattern: Validates operator and registry images
- Difference: Validates infrastructure images, not user-facing workbench images
- Complementary: Our workbench image validation fills a different testing need

### Historical Context

The workbench test suite was created with a focus on notebook controller mechanics (CR creation, sidecar injection, resource management). As the product evolved to include specialized workbench images, the test suite has not kept pace. This RFE addresses that gap by extending the test infrastructure to validate image contents, not just pod creation.

### Success Metrics

**Before this RFE:**
- Test count: 2 tests
- Coverage: Pod creation only
- Image build errors discovered: In production by users

**After this RFE:**
- Test count: 3+ tests (expandable)
- Coverage: Pod creation + image content validation
- Image build errors discovered: In CI before release
- Pattern established: Reusable for future custom images

---

**Customer Considerations**

The primary "customers" for this feature are:

1. **QE/Test Engineers** - Writing and maintaining workbench tests
2. **Workbench Image Team** - Building custom workbench images (instructlab, GPU, etc.)
3. **End Users** - Data scientists using workbench environments (indirect benefit)

### 1. Test Code Maintainability

**Consideration:** The test utility must be easy to understand and extend as new custom images are added.

**Approach:**
- Clear utility function API: `verify_package_in_workbench(pod, package_name, container_name)`
- Comprehensive docstrings with examples
- Follows established patterns from model serving tests (familiar to team)
- README.md provides onboarding guide for new test cases

**Trade-off:** Focused MVP (import verification only) vs full-featured utility (notebook execution). We chose MVP to ship faster and iterate based on actual needs.

### 2. Ownership Boundaries

**Consideration:** Clear separation between test code maintenance (QE) and image builds (workbench team).

**Approach:**
- QE owns: Test code, fixtures, utilities, assertions
- Workbench team owns: Image builds, Dockerfiles, package versions
- Configuration-driven: Image URLs are parameterized, not hardcoded
- Documentation: README.md explicitly defines ownership model

**Handoff Process:**
1. Workbench team provides: Image URL, required packages, version/tag
2. QE team adds: Test parametrization with provided details
3. No cross-team code modifications required

### 3. CI/CD Integration

**Consideration:** Custom image tests are slower (10-minute timeouts) and have external dependencies (registry access).

**Approach:**
- Mark tests with `@pytest.mark.sanity` and `@pytest.mark.slow` (not smoke)
- Run in tier1/sanity suites, not on every PR
- Consider running on merge to main or nightly
- Accept some flakiness risk due to registry availability

**Risk Mitigation:**
- Clear failure messages help debug registry issues
- Retry logic can be added if flakiness becomes problematic
- Test stability monitoring over time

### 4. Upstream vs Downstream Considerations

**Consideration:** Tests must work for both ODH (upstream) and RHOAI (downstream).

**Approach:**
- Existing `pytest_testconfig` handles distribution differences
- Image URLs will differ (ODH vs RHOAI registries)
- Fixtures already support distribution-specific logic (see `minimal_image` fixture)
- Custom image URLs provided via configuration

**No special handling needed:** Pattern already exists for image selection.

### 5. Debugging Experience

**Consideration:** When tests fail, developers need clear, actionable error messages.

**Approach:**
- Layered error handling in `verify_package_in_workbench()`:
  - Pre-flight check: Is pod Running?
  - Capture pod logs on failure
  - Try `pip list` to show installed packages if import fails
  - Clear error messages with troubleshooting hints
- Example: "Failed to import sdg_hub: ModuleNotFoundError. Check that the custom image includes this package."

### 6. Test Isolation and Cleanup

**Consideration:** Ensure tests don't interfere with each other and resources are properly cleaned up.

**Approach:**
- Function-scoped fixtures (existing pattern in conftest.py)
- Context managers handle automatic cleanup
- Each test gets its own namespace (via parametrization)
- No shared state between tests

**Already solved:** Existing fixture infrastructure handles this correctly.

### 7. Scalability to Additional Images

**Consideration:** More custom images will need validation as product evolves (GPU workbenches, domain-specific images).

**Approach:**
- Utility accepts package name as parameter (reusable)
- Test parametrization makes adding new images straightforward
- README.md documents onboarding process
- No fixture modifications needed for new tests

**Future-proof design:** Pattern scales to 10+ custom images without refactoring.

### 8. BLOCKER: Custom Image Availability

**Critical Consideration:** Implementation cannot proceed without knowing the custom image location and ensuring test cluster access.

**Required Actions:**
1. Identify workbench image team contact
2. Get `sdg_hub`-enabled image URL
3. Verify test clusters can pull image
4. Establish image versioning/tagging strategy
5. Document image maintenance ownership

**Status:** This is a **hard blocker** that must be resolved before implementation begins.

### 9. Documentation for Team Adoption

**Consideration:** Team members need clear guidance on when to add custom image tests vs controller tests.

**Approach:**
- README.md with decision flowchart:
  - Testing notebook controller mechanics? → Use `test_spawning.py` patterns
  - Testing custom image contents? → Use `test_custom_images.py` patterns
- Examples for both scenarios
- Clear ownership and handoff documentation

### 10. Test Execution Time Impact

**Consideration:** 10-minute timeouts significantly impact CI runtime.

**Mitigation:**
- Run in sanity suite (not every PR)
- Consider nightly runs for custom image tests
- Parallel test execution where possible
- Document expected runtime in README.md

**Accepted Trade-off:** Longer runtime is acceptable for the value of automated image validation.
