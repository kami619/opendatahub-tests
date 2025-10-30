# Implementation Plan: Workbench Custom Image Introspection Testing

**Branch**: `001-workbench-image-introspection` | **Date**: 2025-10-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-workbench-image-introspection/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Enhance the workbench testing framework to support custom workbench image validation with package introspection capabilities. The primary requirement is to enable test engineers to verify that custom-built workbench images (containing specialized packages like sdg_hub for instructlab workflows) are correctly configured before release. The technical approach involves extending the existing pytest-based test framework with utilities to spawn workbenches using custom image URLs, execute package import verification commands inside running containers, and provide clear diagnostic output when validation fails.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: pytest, openshift-python-wrapper (>=11.0.99), kubernetes Python client, timeout-sampler (>=1.0.6)
**Storage**: N/A (test framework - interacts with Kubernetes cluster state)
**Testing**: pytest with markers (smoke, sanity, slow), pytest-xdist for parallel execution
**Target Platform**: Linux-based test runners executing against OpenShift/Kubernetes clusters (RHOAI/ODH environments)
**Project Type**: Single (test framework extension within existing pytest repository)
**Performance Goals**: Test completion within 12 minutes per custom image validation (10min pod readiness + 1min verification + 1min overhead)
**Constraints**: Must work with unprivileged service account credentials, 10-minute timeout for pod readiness, 1-minute timeout for command execution inside containers
**Scale/Scope**: Extending existing test suite with 3-5 custom image validation test cases, reusable across multiple custom workbench images

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Note**: Project constitution file is not yet customized (`.specify/memory/constitution.md` contains template). Applying general software engineering principles and existing codebase patterns.

### ✓ Reusability & Modularity
- **PASS**: Solution extends existing fixtures (`default_notebook`) with optional parameters rather than creating parallel infrastructure
- **PASS**: Package verification utility will be implemented as a reusable function accepting package names as parameters
- **PASS**: Test parametrization pattern follows existing codebase conventions (`test_spawning.py` parametrization model)

### ✓ Testing Best Practices
- **PASS**: Feature itself is test infrastructure - adds validation capabilities without modifying production code
- **PASS**: Test markers (sanity, slow) properly categorize test execution characteristics
- **PASS**: Clear separation between test fixtures (setup) and test assertions (validation)

### ✓ Maintainability
- **PASS**: Documentation requirements included in functional requirements (FR-010)
- **PASS**: Error messages designed to be actionable with diagnostic information (FR-007, FR-012)
- **PASS**: No breaking changes to existing tests - backward compatibility maintained (FR-008)

### ✓ Simplicity
- **PASS**: MVP focuses on package import verification only (no full notebook execution)
- **PASS**: Reuses existing authentication, RBAC, and namespace fixtures
- **PASS**: No new directory structure or organizational changes required

**Status (Phase 0 - Pre-Research)**: All gates PASS. No constitution violations requiring justification.

**Status (Phase 1 - Post-Design)**: All gates PASS. Design maintains compliance.

### Post-Design Validation

After completing Phase 0 research and Phase 1 design artifacts, re-evaluating constitution compliance:

#### ✓ Reusability & Modularity (Maintained)
- **PASS**: Verification utility (`verify_package_import`) is a pure function accepting parameters
- **PASS**: Test parametrization allows unlimited image variations without code duplication
- **PASS**: Contracts document clear API boundaries for both utility function and fixture

#### ✓ Testing Best Practices (Enhanced)
- **PASS**: Data model defines clear validation flow and error states
- **PASS**: Contracts specify input validation, error handling, and performance requirements
- **PASS**: Quickstart guide enables new contributors to add tests in 15 minutes

#### ✓ Maintainability (Improved)
- **PASS**: Comprehensive documentation suite generated (research.md, data-model.md, contracts/, quickstart.md)
- **PASS**: Clear ownership boundaries documented in quickstart
- **PASS**: API versioning strategy documented in contracts

#### ✓ Simplicity (Maintained)
- **PASS**: Design uses only 2 new entities: utility function + enhanced fixture parameter
- **PASS**: No new infrastructure or services required
- **PASS**: MVP scope strictly maintained - deferred enhancements clearly documented

**Final Status**: PASS - Ready for Phase 2 (task generation via `/speckit.tasks` command)

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
tests/workbenches/
├── __init__.py
├── conftest.py                 # Existing: fixtures for notebooks, PVCs, images
├── utils.py                    # Existing: username helper | NEW: package verification utility
└── notebook-controller/
    ├── test_spawning.py        # Existing: simple spawning, auth customization
    └── test_custom_images.py   # NEW: custom image validation tests

utilities/                      # Existing utilities (if pod exec helpers needed)
├── constants.py
└── infra.py
```

**Structure Decision**: Single project structure - this is a test framework extension within an existing pytest repository. No frontend/backend split. Changes are localized to the `tests/workbenches/` directory with:
- One new test file (`test_custom_images.py`) for custom image validation test cases
- One new utility function in existing `utils.py` for package verification
- Optional enhancement to `conftest.py` fixture to accept custom_image parameter (or handled via parametrization)
- Existing fixtures and utilities reused without modification

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

No violations - this section intentionally left empty. All constitution checks passed.

