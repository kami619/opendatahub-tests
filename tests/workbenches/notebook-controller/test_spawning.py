import pytest
import time
from dataclasses import dataclass

from kubernetes.dynamic.client import DynamicClient

from ocp_resources.pod import Pod, ExecOnPodError
from ocp_resources.namespace import Namespace
from ocp_resources.notebook import Notebook
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from simple_logger.logger import get_logger
from timeout_sampler import TimeoutSampler, TimeoutExpiredError
from utilities.constants import Timeout

LOGGER = get_logger(name=__name__)


# Package configuration for notebook execution testing
STANDARD_PACKAGES = [
    "os",
    "sys",
    "json",
    "datetime"
]

DATA_SCIENCE_PACKAGES = [
    "numpy",
    "pandas",
    "matplotlib",
    "sklearn"
]

PACKAGE_TESTS = {
    "os": "import os; assert hasattr(os, 'path')",
    "sys": "import sys; assert hasattr(sys, 'version')",
    "json": "import json; assert json.dumps({'test': 'value'}) == '{\"test\": \"value\"}'",
    "datetime": "import datetime; assert datetime.datetime.now() is not None",
    "numpy": "import numpy as np; assert np.array([1,2,3]).sum() == 6",
    "pandas": "import pandas as pd; assert len(pd.DataFrame({'a': [1,2,3]})) == 3",
    "matplotlib": "import matplotlib.pyplot as plt; plt.figure()",
    "sklearn": "from sklearn.datasets import make_classification; make_classification(n_samples=10)"
}


@dataclass
class NotebookExecutionResult:
    """Data structure for notebook execution test results"""
    success: bool
    output: str
    error: str | None
    execution_time: float
    package_results: dict[str, bool]


class TestNotebook:
    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
        [
            pytest.param(
                {
                    "name": "test-odh-notebook",
                    "add-dashboard-label": True,
                },
                {"name": "test-odh-notebook"},
                {
                    "namespace": "test-odh-notebook",
                    "name": "test-odh-notebook",
                },
            )
        ],
        indirect=True,
    )
    def test_create_simple_notebook(
        self,
        unprivileged_client: DynamicClient,
        unprivileged_model_namespace: Namespace,
        users_persistent_volume_claim: PersistentVolumeClaim,
        default_notebook: Notebook,
    ):
        """
        Create a simple Notebook CR with all necessary resources and see if the Notebook Operator creates it properly
        """
        notebook_pod = Pod(
            client=unprivileged_client,
            namespace=default_notebook.namespace,
            name=f"{default_notebook.name}-0",
        )
        notebook_pod.wait()
        notebook_pod.wait_for_condition(condition=Pod.Condition.READY, status=Pod.Condition.Status.TRUE)

    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
        [
            pytest.param(
                {
                    "name": "test-auth-notebook",
                    "add-dashboard-label": True,
                },
                {"name": "test-auth-notebook"},
                {
                    "namespace": "test-auth-notebook",
                    "name": "test-auth-notebook",
                    "auth_annotations": {
                        "notebooks.opendatahub.io/auth-sidecar-cpu-request": "200m",
                        "notebooks.opendatahub.io/auth-sidecar-memory-request": "128Mi",
                        "notebooks.opendatahub.io/auth-sidecar-cpu-limit": "500m",
                        "notebooks.opendatahub.io/auth-sidecar-memory-limit": "256Mi",
                    },
                },
            )
        ],
        indirect=True,
    )
    def test_auth_container_resource_customization(
        self,
        unprivileged_client: DynamicClient,
        unprivileged_model_namespace: Namespace,
        users_persistent_volume_claim: PersistentVolumeClaim,
        default_notebook: Notebook,
    ):
        """
        Test that Auth container resource requests and limits can be customized using annotations.

        This test verifies that when a Notebook CR is created with custom Auth container resource
        annotations, the spawned pod has the Auth container with the specified resource values.
        """
        notebook_pod = Pod(
            client=unprivileged_client,
            namespace=default_notebook.namespace,
            name=f"{default_notebook.name}-0",
        )
        notebook_pod.wait()
        notebook_pod.wait_for_condition(condition=Pod.Condition.READY, status=Pod.Condition.Status.TRUE)

        # Verify Auth container has the expected resource values
        auth_container = self._get_auth_container(pod=notebook_pod)
        assert auth_container, "Auth proxy container not found in the pod"

        # Check CPU request
        assert auth_container.resources.requests["cpu"] == "200m", (
            f"Expected CPU request '200m', got '{auth_container.resources.requests['cpu']}'"
        )

        # Check memory request
        assert auth_container.resources.requests["memory"] == "128Mi", (
            f"Expected memory request '128Mi', got '{auth_container.resources.requests['memory']}'"
        )

        # Check CPU limit
        assert auth_container.resources.limits["cpu"] == "500m", (
            f"Expected CPU limit '500m', got '{auth_container.resources.limits['cpu']}'"
        )

        # Check memory limit
        assert auth_container.resources.limits["memory"] == "256Mi", (
            f"Expected memory limit '256Mi', got '{auth_container.resources.limits['memory']}'"
        )

    def _get_auth_container(self, pod: Pod):
        """
        Find and return the Auth proxy container from the pod spec.

        Args:
            pod: The pod instance to search

        Returns:
            The Auth container if found, None otherwise
        """
        containers = pod.instance.spec.containers
        for container in containers:
            if container.name == "kube-rbac-proxy":
                return container
        return None

    def _execute_notebook_code(self, pod: Pod, code: str, timeout: int = Timeout.TIMEOUT_1MIN) -> tuple[bool, str]:
        """
        Execute Python code in the notebook pod using pod.execute() pattern with timeout handling.
        
        Args:
            pod: The notebook pod instance
            code: Python code to execute
            timeout: Execution timeout in seconds (default: 60 seconds per code block)
            
        Returns:
            tuple: (success: bool, output: str)
        """
        try:
            # Use python -c to execute the code directly
            command = ["python", "-c", code]
            
            # Execute with timeout handling using TimeoutSampler pattern
            start_time = time.time()
            
            def _execute_command():
                try:
                    return pod.execute(command=command, ignore_rc=True)
                except ExecOnPodError as e:
                    # Re-raise ExecOnPodError to be handled by outer try-catch
                    raise e
                except Exception as e:
                    # For other exceptions, return None to continue sampling
                    LOGGER.debug(f"Command execution attempt failed: {e}")
                    return None
            
            # Use TimeoutSampler for execution timeout management
            result = None
            try:
                for sample in TimeoutSampler(
                    wait_timeout=timeout,
                    sleep=1,
                    func=_execute_command,
                    exceptions_dict={ExecOnPodError: []}
                ):
                    if sample is not None:
                        result = sample
                        break
            except TimeoutExpiredError:
                execution_time = time.time() - start_time
                error_msg = f"Code execution timeout after {execution_time:.2f}s (limit: {timeout}s)"
                LOGGER.error(error_msg)
                return False, error_msg
            
            execution_time = time.time() - start_time
            LOGGER.debug(f"Code execution completed in {execution_time:.2f}s")
            
            # Check if execution was successful (no error in output)
            if result and not any(error_keyword in result.lower() for error_keyword in ['error', 'exception', 'traceback']):
                LOGGER.debug(f"Code execution successful: {result[:100]}...")
                return True, result
            else:
                LOGGER.error(f"Code execution failed: {result}")
                return False, result or "No output received"
                
        except ExecOnPodError as e:
            error_msg = f"Pod execution failed: {str(e)}"
            LOGGER.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during code execution: {str(e)}"
            LOGGER.error(error_msg)
            return False, error_msg

    def _validate_package_imports(self, pod: Pod) -> dict[str, bool]:
        """
        Validate specific package imports and basic functionality with timeout handling.
        
        Args:
            pod: The notebook pod instance
            
        Returns:
            dict: Package name to success status mapping
        """
        package_results = {}
        
        # Test standard packages first (30 second timeout per package)
        for package in STANDARD_PACKAGES:
            LOGGER.info(f"Testing import of standard package: {package}")
            test_code = PACKAGE_TESTS.get(package, f"import {package}")
            success, output = self._execute_notebook_code(pod, test_code, timeout=Timeout.TIMEOUT_30SEC)
            package_results[package] = success
            
            if not success:
                LOGGER.error(f"Failed to import/test {package}: {output}")
            else:
                LOGGER.debug(f"Successfully imported/tested {package}")
        
        # Test data science packages (60 second timeout per package for heavier imports)
        for package in DATA_SCIENCE_PACKAGES:
            LOGGER.info(f"Testing import of data science package: {package}")
            test_code = PACKAGE_TESTS.get(package, f"import {package}")
            success, output = self._execute_notebook_code(pod, test_code, timeout=Timeout.TIMEOUT_1MIN)
            package_results[package] = success
            
            if not success:
                LOGGER.error(f"Failed to import/test {package}: {output}")
            else:
                LOGGER.debug(f"Successfully imported/tested {package}")
        
        return package_results

    def _wait_for_pod_connection(self, pod: Pod, timeout: int = Timeout.TIMEOUT_30SEC) -> bool:
        """
        Wait for pod connection to be established using TimeoutSampler.
        
        Args:
            pod: The notebook pod instance
            timeout: Connection timeout in seconds (default: 30 seconds for pod connection)
            
        Returns:
            bool: True if connection established, False otherwise
        """
        def _check_pod_connection():
            try:
                # Try a simple command to verify connection
                result = pod.execute(command=["echo", "connection_test"], ignore_rc=True)
                return result is not None
            except ExecOnPodError:
                return False
            except Exception:
                return False
        
        try:
            LOGGER.info(f"Waiting for pod connection (timeout: {timeout}s)...")
            for sample in TimeoutSampler(
                wait_timeout=timeout,
                sleep=2,
                func=_check_pod_connection
            ):
                if sample:
                    LOGGER.info("Pod connection established successfully")
                    return True
        except TimeoutExpiredError:
            LOGGER.error(f"Pod connection timeout after {timeout}s")
            return False
        
        return False

    def _handle_execution_error(self, error: Exception, context: str) -> None:
        """
        Handle and report execution errors with context using existing logger patterns.
        Provides specific error handling for different error types.
        
        Args:
            error: The exception that occurred
            context: Context description for debugging
        """
        # Categorize error types for better reporting
        if isinstance(error, TimeoutExpiredError):
            error_msg = f"Timeout error in {context}: {str(error)}"
            LOGGER.error(error_msg)
        elif isinstance(error, ExecOnPodError):
            error_msg = f"Pod execution error in {context}: {str(error)}"
            LOGGER.error(error_msg)
        elif "pod not ready" in str(error).lower():
            error_msg = f"Pod not ready error in {context}: {str(error)}"
            LOGGER.error(error_msg)
        elif "connection" in str(error).lower():
            error_msg = f"Connection failed error in {context}: {str(error)}"
            LOGGER.error(error_msg)
        elif "import" in str(error).lower():
            error_msg = f"Import error in {context}: {str(error)}"
            LOGGER.error(error_msg)
        else:
            error_msg = f"Notebook execution failed in {context}: {str(error)}"
            LOGGER.error(error_msg)
        
        pytest.fail(error_msg)

    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "unprivileged_model_namespace,users_persistent_volume_claim,default_notebook",
        [
            pytest.param(
                {
                    "name": "test-notebook-execution",
                    "add-dashboard-label": True,
                },
                {"name": "test-notebook-execution"},
                {
                    "namespace": "test-notebook-execution", 
                    "name": "test-notebook-execution",
                },
            )
        ],
        indirect=True,
    )
    def test_notebook_package_import_execution(
        self,
        unprivileged_client: DynamicClient,
        unprivileged_model_namespace: Namespace,
        users_persistent_volume_claim: PersistentVolumeClaim,
        default_notebook: Notebook,
    ):
        """
        Test that spawned notebooks can execute code with package imports.
        
        This test verifies that a notebook pod can successfully import and use
        common Python packages, ensuring the notebook environment is properly
        configured with necessary dependencies.
        
        Timeout Management:
        - Overall test timeout: 5 minutes for complete test
        - Pod connection timeout: 30 seconds for pod connection
        - Execution timeout: 60 seconds per code block
        """
        start_time = time.time()
        overall_timeout = Timeout.TIMEOUT_5MIN  # 5 minutes for complete test
        
        def _check_overall_timeout():
            elapsed = time.time() - start_time
            if elapsed > overall_timeout:
                raise TimeoutExpiredError(f"Overall test timeout exceeded: {elapsed:.2f}s > {overall_timeout}s")
        
        try:
            # Setup Phase: Wait for notebook pod readiness
            LOGGER.info("Starting notebook package import execution test")
            _check_overall_timeout()
            
            notebook_pod = Pod(
                client=unprivileged_client,
                namespace=default_notebook.namespace,
                name=f"{default_notebook.name}-0",
            )
            
            LOGGER.info("Waiting for notebook pod to be ready...")
            try:
                notebook_pod.wait()
                notebook_pod.wait_for_condition(
                    condition=Pod.Condition.READY, 
                    status=Pod.Condition.Status.TRUE,
                    timeout=Timeout.TIMEOUT_5MIN  # 5 minutes timeout for pod readiness
                )
                LOGGER.info("Notebook pod is ready")
            except Exception as e:
                self._handle_execution_error(e, "pod readiness check")
            
            _check_overall_timeout()
            
            # Connection Phase: Establish pod connection with timeout
            LOGGER.info("Establishing pod connection...")
            if not self._wait_for_pod_connection(notebook_pod, timeout=Timeout.TIMEOUT_30SEC):
                self._handle_execution_error(
                    Exception("Failed to establish pod connection"), 
                    "pod connection establishment"
                )
            
            _check_overall_timeout()
            
            # Wait additional time for notebook server to be fully initialized
            LOGGER.info("Waiting for notebook server initialization...")
            time.sleep(30)
            
            _check_overall_timeout()
            
            # Import Testing Phase: Execute standard library and data science package tests
            LOGGER.info("Starting package import validation...")
            try:
                package_results = self._validate_package_imports(notebook_pod)
            except Exception as e:
                self._handle_execution_error(e, "package import validation")
            
            _check_overall_timeout()
            
            # Validation Phase: Verify all imports and basic functionality
            failed_packages = [pkg for pkg, success in package_results.items() if not success]
            successful_packages = [pkg for pkg, success in package_results.items() if success]
            
            LOGGER.info(f"Package import results: {len(successful_packages)} successful, {len(failed_packages)} failed")
            
            if successful_packages:
                LOGGER.info(f"Successfully imported packages: {', '.join(successful_packages)}")
            
            if failed_packages:
                error_msg = f"Failed to import packages: {', '.join(failed_packages)}"
                LOGGER.error(error_msg)
                
                # Log detailed failure information
                for pkg in failed_packages:
                    LOGGER.error(f"Package {pkg} import failed - this may indicate missing dependencies in the notebook environment")
                
                self._handle_execution_error(Exception(error_msg), "package import validation")
            
            # Verify minimum required packages are working
            required_standard_packages = ["os", "sys", "json"]
            missing_required = [pkg for pkg in required_standard_packages if not package_results.get(pkg, False)]
            
            if missing_required:
                error_msg = f"Critical standard library packages failed: {', '.join(missing_required)}"
                LOGGER.error(error_msg)
                self._handle_execution_error(Exception(error_msg), "critical package validation")
            
            LOGGER.info("All package imports and basic functionality tests passed successfully")
            
        except TimeoutExpiredError as e:
            self._handle_execution_error(e, "overall test timeout")
        except Exception as e:
            self._handle_execution_error(e, "notebook package import execution test")
        
        finally:
            # Cleanup and execution summary logging
            execution_time = time.time() - start_time
            LOGGER.info(f"Notebook package import execution test completed in {execution_time:.2f} seconds")
            
            if execution_time > overall_timeout:
                LOGGER.warning(f"Test execution time ({execution_time:.2f}s) exceeded overall timeout ({overall_timeout}s)")
            
            if 'package_results' in locals():
                total_packages = len(package_results)
                successful_count = sum(1 for success in package_results.values() if success)
                LOGGER.info(f"Final summary: {successful_count}/{total_packages} packages imported successfully")
            else:
                LOGGER.warning("Test completed without package results due to early failure")
