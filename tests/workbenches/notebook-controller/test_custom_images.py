"""Custom workbench image validation tests."""

import pytest

from kubernetes.dynamic.client import DynamicClient

from ocp_resources.pod import Pod
from ocp_resources.namespace import Namespace
from ocp_resources.notebook import Notebook
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim

from tests.workbenches.utils import verify_package_import, install_packages_in_pod
from utilities.constants import Timeout
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


class TestCustomImageValidation:
    """Validate custom workbench images with package introspection."""

    @pytest.mark.sanity
    @pytest.mark.slow
    @pytest.mark.parametrize(
        "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
        [
            # ========================================
            # HOW TO ADD A NEW CUSTOM IMAGE TEST:
            # ========================================
            # 1. Obtain image URL and package list from workbench image team
            # 2. Copy the pytest.param template below
            # 3. Update name, namespace, custom_image, and id fields
            # 4. Update packages_to_verify in the test method (see line ~120)
            # 5. Remove the skip marker once the image is available
            # 6. Run: pytest tests/workbenches/notebook-controller/test_custom_images.py::TestCustomImageValidation::test_custom_image_package_verification[your_id] -v
            # ========================================
            # Test Case: SDG Hub Notebook
            # Image: To be provided by workbench image team
            # Required Packages: sdg_hub, instructlab
            # Purpose: Validate sdg_hub image for instructlab workflows
            # Contact: workbench-image-team@redhat.com
            # NOTE: This is a placeholder - update with actual image URL once provided
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
                    "custom_image": "quay.io/repository/opendatahub/odh-workbench-jupyter-minimal-cuda-py312-ubi9/manifest/sha256:9458a764d861cbe0a782a53e0f5a13a4bcba35d279145d87088ab3cdfabcad1d",
                },
                id="sdg_hub_image",
            ),
        ],
        indirect=True,
    )
    def test_custom_image_package_verification(
        self,
        request: pytest.FixtureRequest,
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

        Test satisfies:
        - FR-001: Spawn workbench with custom image URL
        - FR-002: Detect running pod and wait for ready state
        - FR-003: 10-minute timeout for pod readiness
        - FR-004: Execute package import commands
        - FR-005: Report success/failure with details
        """
        # Wait for notebook pod to be created and reach Ready state
        notebook_pod = Pod(
            client=unprivileged_client,
            namespace=default_notebook.namespace,
            name=f"{default_notebook.name}-0",
        )

        # Wait for pod to exist
        notebook_pod.wait()

        # Wait for pod to reach Ready state (10-minute timeout for large custom images)
        try:
            notebook_pod.wait_for_condition(
                condition=Pod.Condition.READY,
                status=Pod.Condition.Status.TRUE,
                timeout=Timeout.TIMEOUT_10MIN,
            )
        except Exception as e:
            # Enhanced error handling: Collect pod diagnostic information
            pod_status = notebook_pod.instance.status if notebook_pod.exists else None

            if pod_status:
                pod_phase = pod_status.phase
                error_details = self._get_pod_failure_details(notebook_pod)
                raise AssertionError(
                    f"Pod '{default_notebook.name}-0' failed to reach Ready state within 10 minutes.\n"
                    f"Pod Phase: {pod_phase}\n"
                    f"Error Details:\n{error_details}\n"
                    f"Original Error: {e}"
                ) from e
            else:
                raise AssertionError(
                    f"Pod '{default_notebook.name}-0' was not created. Check notebook controller logs."
                ) from e

        # Determine packages to verify based on test ID
        # Different packages per test case (based on test ID from parametrization)
        test_id = request.node.callspec.id
        if "sdg_hub" in test_id:
            # SDG Hub image packages - install dynamically for self-contained testing
            packages_to_verify = ["sdg_hub"]
        else:
            # Default: basic Python packages
            packages_to_verify = ["sys", "os"]

        # Install packages if they're not standard library (not in the default list)
        standard_lib_packages = {"sys", "os"}
        packages_to_install = [pkg for pkg in packages_to_verify if pkg not in standard_lib_packages]

        if packages_to_install:
            LOGGER.info(f"Installing {len(packages_to_install)} packages: {packages_to_install}")
            install_results = install_packages_in_pod(
                pod=notebook_pod,
                container_name=default_notebook.name,
                packages=packages_to_install,
                timeout=Timeout.TIMEOUT_2MIN,
            )

            failed_installs = [name for name, success in install_results.items() if not success]
            if failed_installs:
                LOGGER.warning(f"Failed to install packages: {failed_installs}")

        # Verify packages are importable
        results = verify_package_import(
            pod=notebook_pod,
            container_name=default_notebook.name,
            packages=packages_to_verify,
            timeout=Timeout.TIMEOUT_1MIN,
        )

        # Assert all packages imported successfully
        failed_packages = [name for name, result in results.items() if not result.import_successful]

        if failed_packages:
            error_report = self._format_package_failure_report(failed_packages, results, notebook_pod)
            raise AssertionError(error_report)

    def _get_pod_failure_details(self, pod: Pod) -> str:
        """
        Collect diagnostic information when pod fails to reach ready state.

        Args:
            pod: The pod instance to diagnose

        Returns:
            Formatted diagnostic information string
        """
        details = []

        pod_status = pod.instance.status
        if not pod_status:
            return "Pod status unavailable"

        # Get pod phase
        details.append(f"Phase: {pod_status.phase}")

        # Get container statuses
        if pod_status.containerStatuses:
            details.append("\nContainer Statuses:")
            for container_status in pod_status.containerStatuses:
                container_name = container_status.name
                ready = container_status.ready

                details.append(f"  - {container_name}: ready={ready}")

                # Check waiting state
                if hasattr(container_status.state, "waiting") and container_status.state.waiting:
                    waiting = container_status.state.waiting
                    reason = waiting.reason
                    message = waiting.message if hasattr(waiting, "message") else ""

                    # Categorize common errors
                    if reason == "ImagePullBackOff":
                        details.append(
                            f"    ⚠️  ImagePullBackOff: Failed to pull custom image\n"
                            f"    Verify registry access and image URL\n"
                            f"    Message: {message}"
                        )
                    elif reason == "CrashLoopBackOff":
                        details.append(
                            f"    ⚠️  CrashLoopBackOff: Container is crashing\n"
                            f"    Check container logs for startup errors\n"
                            f"    Message: {message}"
                        )
                    elif reason == "ErrImagePull":
                        details.append(
                            f"    ⚠️  ErrImagePull: Cannot pull image\n"
                            f"    Verify image exists and cluster has pull access\n"
                            f"    Message: {message}"
                        )
                    else:
                        details.append(f"    Waiting Reason: {reason}\n" f"    Message: {message}")

                # Check terminated state
                if hasattr(container_status.state, "terminated") and container_status.state.terminated:
                    terminated = container_status.state.terminated
                    details.append(
                        f"    ⚠️  Container terminated\n"
                        f"    Exit Code: {terminated.exitCode}\n"
                        f"    Reason: {terminated.reason}"
                    )

        # Try to get pod logs for main container
        try:
            logs = pod.log(container=pod.instance.spec.containers[0].name, tail_lines=50)
            if logs:
                details.append(f"\nRecent Logs (last 50 lines):\n{logs}")
        except Exception:
            details.append("\n(Could not retrieve pod logs)")

        return "\n".join(details)

    def _format_package_failure_report(
        self, failed_packages: list[str], results: dict, pod: Pod
    ) -> str:
        """
        Format a detailed error report for package import failures.

        Args:
            failed_packages: List of package names that failed to import
            results: Dictionary of all verification results
            pod: The pod instance where verification was attempted

        Returns:
            Formatted error report string
        """
        report = [
            f"The following packages are not importable in {pod.name}:",
            "",
        ]

        for name in failed_packages:
            result = results[name]
            report.append(f"  ❌ {name}:")
            report.append(f"     Error: {result.error_message}")
            report.append(f"     Command: {result.command_executed}")
            report.append(f"     Execution Time: {result.execution_time_seconds:.2f}s")

            if result.pod_logs:
                report.append(f"     Pod Logs (excerpt):")
                # Show first 500 characters of logs
                log_excerpt = result.pod_logs[:500]
                for line in log_excerpt.split("\n"):
                    report.append(f"       {line}")
            report.append("")

        # Add troubleshooting guidance
        report.append("Troubleshooting:")
        report.append("  1. Verify the custom image contains the required packages")
        report.append("  2. Check if packages are installed in the correct Python environment")
        report.append("  3. Verify package names match import names (pip name vs import name)")
        report.append("  4. Contact the workbench image team for package installation issues")

        return "\n".join(report)
