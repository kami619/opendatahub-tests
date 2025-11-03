---
description: "Task list for Workbench Custom Image Introspection Testing implementation"
---

# Tasks: Workbench Custom Image Introspection Testing

**Input**: Design documents from `/specs/001-workbench-image-introspection/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: This feature IS the test infrastructure itself. No separate test tasks are included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions
- Test framework at repository root: `tests/workbenches/`
- This is an existing pytest repository - extending test suite with new capabilities

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Minimal project setup - most infrastructure already exists

- [ ] T001 Verify existing test structure and identify blocker for custom image URL
- [ ] T002 Coordinate with workbench image team to obtain sdg_hub image URL and package list

**Checkpoint**: Image URL obtained - implementation can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core utilities and fixtures that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Create PackageVerificationResult dataclass in tests/workbenches/utils.py
- [ ] T004 Implement verify_package_import utility function in tests/workbenches/utils.py
- [ ] T005 Enhance default_notebook fixture in tests/workbenches/conftest.py to accept custom_image parameter
- [ ] T006 Add input validation to default_notebook fixture for custom_image parameter

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Test Engineer Validates Custom Workbench Image (Priority: P1) 🎯 MVP

**Goal**: Enable test engineers to verify custom workbench images contain required packages

**Independent Test**: Spawn workbench with custom image URL, wait for pod readiness, execute package import command, verify successful import

### Implementation for User Story 1

- [ ] T007 [US1] Create test_custom_images.py file in tests/workbenches/notebook-controller/ with TestCustomImageValidation class
- [ ] T008 [US1] Implement test_custom_image_package_verification test method with parametrization for sdg_hub image
- [ ] T009 [US1] Add pod readiness waiting logic with 10-minute timeout using wait_for_condition in test_custom_image_package_verification
- [ ] T010 [US1] Integrate verify_package_import utility call in test_custom_image_package_verification
- [ ] T011 [US1] Add assertion logic for package verification results with detailed failure messages
- [ ] T012 [US1] Add pytest markers (@pytest.mark.sanity and @pytest.mark.slow) to test_custom_image_package_verification
- [ ] T013 [US1] Add pod diagnostic error handling for ImagePullBackOff and CrashLoopBackOff scenarios

**Checkpoint**: User Story 1 complete - can validate custom images with package introspection

---

## Phase 4: User Story 2 - Test Engineer Adds Validation for New Custom Image (Priority: P2)

**Goal**: Demonstrate test framework scalability by adding second custom image validation

**Independent Test**: Add new parametrized test case for different custom image, run test, verify it works without modifying shared fixtures

### Implementation for User Story 2

- [ ] T014 [US2] Add second parametrized test case to test_custom_image_package_verification for GPU or domain-specific image
- [ ] T015 [US2] Document parametrization pattern in test file comments explaining how to add new images
- [ ] T016 [US2] Verify backward compatibility by running existing test_spawning.py tests

**Checkpoint**: User Story 2 complete - pattern reusability demonstrated

---

## Phase 5: User Story 3 - Developer Debugs Failed Custom Image Test (Priority: P2)

**Goal**: Provide clear, actionable diagnostic information when tests fail

**Independent Test**: Create intentionally broken custom image (missing package or bad URL), run validation test, verify failure output includes pod status, logs, and troubleshooting guidance

### Implementation for User Story 3

- [ ] T017 [US3] Enhance verify_package_import to collect pod logs on package import failure
- [ ] T018 [US3] Add error categorization logic in test_custom_image_package_verification for ImagePullBackOff detection
- [ ] T019 [US3] Add error categorization logic in test_custom_image_package_verification for pod timeout scenarios
- [ ] T020 [US3] Implement diagnostic output formatting with pod phase, container status, and logs in assertion messages
- [ ] T021 [US3] Add optional installed packages listing on import failure using pip list command
- [ ] T022 [US3] Create test case demonstrating diagnostic output quality with intentionally broken image

**Checkpoint**: User Story 3 complete - failure scenarios provide actionable debugging information

---

## Phase 6: User Story 4 - QE Team Maintains Test Suite Documentation (Priority: P3)

**Goal**: Enable team scalability through comprehensive documentation

**Independent Test**: New team member reads README, follows guide, successfully adds test case in under 15 minutes

### Implementation for User Story 4

- [ ] T023 [P] [US4] Create or enhance tests/workbenches/README.md with directory structure explanation
- [ ] T024 [P] [US4] Add "Custom Image Validation Tests" section to README with purpose and usage
- [ ] T025 [P] [US4] Document step-by-step guide for adding new custom image tests in README
- [ ] T026 [P] [US4] Add ownership boundaries documentation explaining QE vs Image Team responsibilities
- [ ] T027 [P] [US4] Include troubleshooting section in README for common failure scenarios
- [ ] T028 [P] [US4] Add example test parametrization with annotations in README

**Checkpoint**: Documentation complete - team members can onboard independently

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final refinements affecting multiple user stories

- [ ] T029 [P] Add type hints to all new functions in utils.py and test_custom_images.py
- [ ] T030 [P] Review and enhance error messages across all test assertions for clarity
- [ ] T031 Validate implementation against all functional requirements (FR-001 through FR-012 in spec.md)
- [ ] T032 Run complete workbench test suite to ensure no regressions
- [ ] T033 Verify test execution time meets success criteria (12 minutes maximum per test case)
- [ ] T034 Add inline code comments explaining complex logic in verify_package_import
- [ ] T035 Review quickstart.md guide and update if implementation differs from design

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately (BLOCKER: requires image URL from external team)
- **Foundational (Phase 2)**: Depends on Setup completion (image URL obtained) - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories CAN proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P2 → P3)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Should work independently of US1 but typically runs after US1 to demonstrate pattern reuse
- **User Story 3 (P2)**: Enhances US1 implementation - can start after US1 complete OR in parallel if US1 tasks are coordinated
- **User Story 4 (P3)**: Documents all stories - should be done after US1-3 are implemented to ensure accuracy

### Within Each User Story

**User Story 1**:
- T007 (create file) → T008 (implement test method) → T009-T012 (enhance test method) → T013 (error handling)
- T009, T010, T011 can be done together in test method implementation
- T012 (markers) and T013 (error handling) can be done in parallel after T008-T011

**User Story 2**:
- T014 (add second test case) can start immediately
- T015 and T016 can run in parallel after T014

**User Story 3**:
- T017 (enhance utility) independent
- T018-T021 enhance test method, can be done together
- T022 (demo test) after T017-T021

**User Story 4**:
- All tasks (T023-T028) marked [P] - can run in parallel (all edit README.md but different sections)

### Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel (different focus areas)
- **Phase 2**: T003 and T004 can run together (same file), T005 and T006 can run together (same file)
- **User Story 1**: T012 and T013 can run in parallel after T011 complete
- **User Story 2**: T015 and T016 can run in parallel after T014
- **User Story 4**: ALL tasks (T023-T028) can run in parallel - all documentation sections are independent
- **Phase 7**: T029, T030, T034 can run in parallel (different files or different functions)

---

## Parallel Example: User Story 4 (Documentation)

```bash
# Launch all documentation tasks together:
Task: "Create or enhance tests/workbenches/README.md with directory structure explanation"
Task: "Add 'Custom Image Validation Tests' section to README with purpose and usage"
Task: "Document step-by-step guide for adding new custom image tests in README"
Task: "Add ownership boundaries documentation explaining QE vs Image Team responsibilities"
Task: "Include troubleshooting section in README for common failure scenarios"
Task: "Add example test parametrization with annotations in README"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (including blocker resolution for image URL)
2. Complete Phase 2: Foundational (utility + fixture enhancement)
3. Complete Phase 3: User Story 1 (core validation capability)
4. **STOP and VALIDATE**: Test custom image validation independently
5. Demo capability to stakeholders

**MVP Delivers**: Ability to validate one custom workbench image with package introspection

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test sdg_hub image → Demo (MVP!)
3. Add User Story 2 → Add second image → Demo scalability
4. Add User Story 3 → Break image intentionally → Demo diagnostics
5. Add User Story 4 → Documentation → Team self-service enabled
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (T001-T006)
2. Once Foundational is done:
   - Developer A: User Story 1 (T007-T013) - Core validation
   - Developer B: User Story 4 (T023-T028) - Documentation (can start after US1 design is clear)
3. After User Story 1 complete:
   - Developer A: User Story 2 (T014-T016) - Demonstrate pattern
   - Developer B: User Story 3 (T017-T022) - Enhanced diagnostics
4. Team converges on Phase 7 Polish

---

## Critical Blocker Tracking

**BLOCKER (from spec.md - Dependencies and Blockers)**:
- Task T002: Custom workbench image URL with sdg_hub package must be provided by workbench image team
- **Impact**: Cannot proceed beyond Phase 1 without image URL
- **Owner**: External workbench image team
- **Required Information**:
  - Full registry URL (e.g., `quay.io/opendatahub/sdg-hub-notebook:2025.1`)
  - Image tag/version
  - List of required packages to verify (e.g., `["sdg_hub", "instructlab"]`)
- **Mitigation**: Have all other infrastructure ready so implementation can proceed immediately once URL is provided

---

## Success Criteria Validation

Each user story maps to success criteria from spec.md:

**User Story 1 (P1)**:
- SC-001: Single test run validation ✓ (T008-T013)
- SC-002: 12-minute completion time ✓ (T033 validates)
- SC-003: Detect missing packages before release ✓ (T010-T011)

**User Story 2 (P2)**:
- SC-004: Add new image in <15 minutes ✓ (T014-T016)
- SC-006: Multiple test cases ✓ (T014)

**User Story 3 (P2)**:
- SC-005: Diagnostic info for 30-min fixes ✓ (T017-T022)
- SC-007: Categorized failures ✓ (T018-T020)

**User Story 4 (P3)**:
- SC-008: Documentation feedback ✓ (T023-T028)

---

## Task Estimation

**Total Tasks**: 35 tasks
- Phase 1 (Setup): 2 tasks (~1-2 hours, blocked on external team)
- Phase 2 (Foundational): 4 tasks (~3-4 hours)
- Phase 3 (User Story 1): 7 tasks (~6-8 hours)
- Phase 4 (User Story 2): 3 tasks (~2-3 hours)
- Phase 5 (User Story 3): 6 tasks (~4-6 hours)
- Phase 6 (User Story 4): 6 tasks (~3-4 hours)
- Phase 7 (Polish): 7 tasks (~2-3 hours)

**Total Estimated Effort**: 21-30 hours (single developer, sequential)

**With Parallel Execution**: 12-18 hours (2 developers)

**MVP Only (US1)**: 9-14 hours (Setup + Foundational + US1)

---

## Notes

- [P] tasks = different files or different functions, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- This is a test framework extension - no separate tests for the tests
- Existing tests (test_spawning.py) must continue to pass
- Custom image tests marked as sanity + slow (not smoke)
- 10-minute timeout for pod readiness, 1-minute timeout for package verification
- All tasks use existing infrastructure - minimal new files
- Documentation is critical for team adoption (User Story 4)
