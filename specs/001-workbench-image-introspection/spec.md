# Feature Specification: Workbench Custom Image Introspection Testing

**Feature Branch**: `001-workbench-image-introspection`
**Created**: 2025-10-30
**Status**: Draft
**Input**: User description: "Enhance workbench testing to validate custom images with package introspection"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Test Engineer Validates Custom Workbench Image (Priority: P1)

A test engineer needs to verify that a newly built custom workbench image (containing sdg_hub package) is correctly configured and can be used by data scientists for instructlab workflows.

**Why this priority**: This is the core capability - without validated custom images, users may encounter broken environments in production. This delivers immediate value by catching image build errors before release.

**Independent Test**: Can be fully tested by spawning a workbench with a specific custom image URL, waiting for pod readiness, executing a package import command inside the container, and verifying successful import - delivers confidence that the custom image contains required dependencies.

**Acceptance Scenarios**:

1. **Given** a test cluster with the notebook controller deployed and a custom workbench image URL available, **When** the test engineer runs the custom image validation test with sdg_hub package verification, **Then** the test spawns a workbench pod using the custom image, executes `python -c "import sdg_hub"` inside the container, and passes when the import succeeds without errors
2. **Given** a custom workbench image that is missing the sdg_hub package, **When** the test engineer runs the validation test, **Then** the test fails with a clear error message indicating the package is not importable, includes pod logs for debugging, and optionally lists installed packages
3. **Given** a custom image URL that is inaccessible or does not exist, **When** the test engineer runs the validation test, **Then** the test waits up to 10 minutes for pod readiness, detects the ImagePullBackOff state, and fails with a descriptive error message indicating registry access or image URL issues

---

### User Story 2 - Test Engineer Adds Validation for New Custom Image (Priority: P2)

A test engineer needs to add validation for a newly created GPU-enabled or domain-specific workbench image to the test suite without modifying shared fixtures or utilities.

**Why this priority**: Scalability is essential - the test framework must support multiple custom images as the product expands. This demonstrates the reusability of the testing pattern and ensures maintainability.

**Independent Test**: Can be fully tested by creating a new test case with custom image parametrization, reusing the existing package verification utility, and running the test to confirm the new image validation works without changes to existing tests.

**Acceptance Scenarios**:

1. **Given** a new custom workbench image (e.g., GPU-enabled) is available with specific package requirements, **When** the test engineer adds a new parametrized test case specifying the image URL and package names to verify, **Then** the test successfully validates the new image without requiring modifications to shared fixtures or utilities
2. **Given** the test engineer follows the documentation in the workbench README, **When** they add the new test case following the established pattern, **Then** they can complete the addition in under 15 minutes using only parametrization changes and reusing existing utilities

---

### User Story 3 - Developer Debugs Failed Custom Image Test (Priority: P2)

A workbench image developer encounters a test failure when validating a custom image and needs actionable information to diagnose and fix the problem.

**Why this priority**: Clear error reporting reduces debugging time and improves developer experience. This is critical for adoption of the testing pattern but secondary to the core validation capability.

**Independent Test**: Can be fully tested by intentionally creating a broken custom image (missing package or bad URL), running the validation test, and verifying that the failure output includes pod status, pod logs, error messages, and troubleshooting guidance.

**Acceptance Scenarios**:

1. **Given** a custom image build that inadvertently excluded the sdg_hub package, **When** the validation test fails during package import, **Then** the error message clearly states which package failed to import, includes the ModuleNotFoundError details from the container, attempts to list installed packages for comparison, and provides guidance on checking the image build process
2. **Given** a pod that fails to reach Running state due to resource constraints or scheduling issues, **When** the test times out after 10 minutes, **Then** the error message includes the pod phase (Pending/Failed), pod events showing scheduling or resource errors, and guidance on checking cluster resources or image size

---

### User Story 4 - QE Team Maintains Test Suite Documentation (Priority: P3)

QE team members and new contributors need clear documentation explaining the workbench test structure, ownership boundaries, and how to add new custom image tests.

**Why this priority**: Documentation enables team scalability and knowledge transfer but is less urgent than functional validation. Can be completed after initial implementation.

**Independent Test**: Can be fully tested by reviewing the README documentation, following the "adding new tests" guide without prior context, and successfully adding a test case using only the documentation as reference.

**Acceptance Scenarios**:

1. **Given** a new QE team member unfamiliar with the workbench test suite, **When** they read the workbenches/README.md file, **Then** they understand the directory structure, the difference between notebook controller tests and custom image validation tests, ownership boundaries between QE and image teams, and the process for adding new test cases
2. **Given** a workbench image team member needs test coverage for a new image, **When** they consult the documentation, **Then** they understand what information to provide to the QE team (image URL, required packages, version/tag), who owns what parts of the implementation, and expected timeline for test integration

---

### Edge Cases

- What happens when the custom image pull takes longer than 10 minutes due to large size or registry throttling?
- How does the test handle a pod that becomes Running but the main container crashes immediately after?
- What if the package import command hangs indefinitely inside the container?
- How does the system differentiate between package not installed vs package installed but missing system dependencies (import fails due to missing .so files)?
- What happens when the test cluster lacks permissions to execute commands in pods?
- How does the test behave when testing multiple packages and only some are missing?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The test infrastructure MUST support spawning workbench notebooks with custom image URLs provided via test parametrization
- **FR-002**: The test infrastructure MUST execute Python import commands inside running workbench containers to verify package availability
- **FR-003**: Tests MUST wait up to 10 minutes for custom image pods to reach Running state to accommodate large image pulls
- **FR-004**: Tests MUST execute package verification commands with a 1-minute timeout to prevent indefinite hangs
- **FR-005**: The test framework MUST capture and report pod logs when validation fails for debugging purposes
- **FR-006**: The package verification utility MUST be reusable across multiple test cases and accept package name as a parameter
- **FR-007**: Tests MUST fail with clear, actionable error messages when packages are not importable or pods fail to start
- **FR-008**: The existing notebook controller tests (simple spawning and auth customization) MUST continue to pass without modification
- **FR-009**: Custom image validation tests MUST be marked with appropriate test markers (sanity and slow, not smoke) to control CI execution
- **FR-010**: The test suite MUST include documentation explaining test structure, ownership model, and onboarding process for adding new custom image tests
- **FR-011**: The default_notebook fixture MUST accept an optional custom_image parameter to override the default minimal image
- **FR-012**: Validation failures due to missing packages MUST include diagnostic information such as the list of installed packages when possible

### Key Entities

- **Custom Workbench Image**: A container image containing specialized packages (like sdg_hub) for specific data science workflows (e.g., instructlab, GPU computing). Identified by registry URL and tag.
- **Workbench Pod**: A Kubernetes pod created by the notebook controller from a Notebook custom resource, running the workbench container and authentication sidecars.
- **Package Verification Result**: The outcome of executing a package import test inside a workbench container, including success/failure status, command output, error messages, and pod state.
- **Test Configuration**: Parametrization data specifying namespace, notebook name, custom image URL, and packages to verify for a specific test case.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Test engineers can validate a custom workbench image with package introspection in a single test run without manual intervention
- **SC-002**: Custom image validation tests complete within 12 minutes per test case (10 minutes for pod readiness + 1 minute for verification + 1 minute overhead)
- **SC-003**: Image build errors (missing packages) are detected automatically in CI before release rather than by end users in production
- **SC-004**: Test engineers can add validation for a new custom image by creating a new test case with parametrization in under 15 minutes without modifying shared utilities
- **SC-005**: Failed validation tests provide sufficient diagnostic information (error messages, pod logs, installed packages) for developers to identify and fix issues within 30 minutes
- **SC-006**: The test suite maintains at least 3 custom image validation test cases (starting with sdg_hub) demonstrating the pattern's reusability
- **SC-007**: Test execution failures are clearly categorized (image pull issues, pod startup failures, package import failures) with specific error messages for each category
- **SC-008**: Test suite documentation receives positive feedback from at least 2 new contributors who successfully add test cases using only the documentation as guidance

## Assumptions

- Custom workbench images are hosted in container registries accessible from the test cluster (quay.io or similar)
- The unprivileged test service account has sufficient permissions to execute commands in pods (already established pattern in the repository)
- Custom images use Python as the primary runtime for package verification (consistent with data science workbench use cases)
- Image tags follow semantic versioning or date-based naming conventions for stability
- Test clusters have sufficient resources to pull and run multi-GB custom images
- The workbench image team will provide image URLs and required package lists as input to test configuration
- Package import verification (`python -c "import package_name"`) is sufficient for MVP validation (full notebook execution deferred to future enhancements)

## Out of Scope

- Building or maintaining custom workbench images (owned by workbench image team)
- Executing full notebook examples end-to-end with cell-by-cell validation (future enhancement)
- Testing non-Python packages or packages requiring GUI interaction
- Generic script execution framework for arbitrary commands (MVP focuses on package import)
- Creating separate directory structure for image tests (keeping tests in notebook-controller directory)
- Performance testing or benchmarking of workbench operations
- Testing workbench functionality beyond package availability (e.g., JupyterLab features, kernel management)
- Automated image building or CI/CD pipeline integration for custom images

## Dependencies and Blockers

- **CRITICAL BLOCKER**: Custom workbench image URL with sdg_hub package must be identified and provided by workbench image team before implementation can proceed
- **Dependency**: Test clusters must have network access to pull custom images from the specified registry
- **Dependency**: Coordination with workbench image team to establish image versioning and tagging strategy
- **Dependency**: Verification that unprivileged_client credentials have pod exec permissions (assumed to be already configured based on existing patterns)

