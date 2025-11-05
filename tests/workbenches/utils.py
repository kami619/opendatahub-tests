import re
import shlex
from dataclasses import dataclass
from time import time

from kubernetes.dynamic import DynamicClient
from ocp_resources.pod import Pod
from ocp_resources.pod import ExecOnPodError
from ocp_resources.self_subject_review import SelfSubjectReview
from ocp_resources.user import User
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


@dataclass
class PackageVerificationResult:
    """Represents the outcome of package import verification for a single package."""

    package_name: str
    import_successful: bool
    error_message: str | None
    command_executed: str
    execution_time_seconds: float
    pod_logs: str | None
    stdout: str = ""
    stderr: str = ""


def verify_package_import(
    pod: Pod,
    container_name: str,
    packages: list[str],
    timeout: int = 60,
    collect_diagnostics: bool = True,
) -> dict[str, PackageVerificationResult]:
    """
    Verify that specified Python packages are importable in a pod container.

    This function executes 'python -c "import <package>"' for each package
    in the provided list and returns verification results.

    Args:
        pod: Pod instance to execute commands in (from ocp_resources.pod)
        container_name: Name of the container within the pod to target
        packages: List of Python package names to verify (e.g., ["sdg_hub", "numpy"])
        timeout: Maximum time in seconds to wait for each import command (default: 60)
        collect_diagnostics: Whether to collect pod logs on failure (default: True)

    Returns:
        Dictionary mapping package names to PackageVerificationResult objects.

    Raises:
        ValueError: If packages list is empty or contains invalid identifiers
        RuntimeError: If pod is not in Running state or container doesn't exist

    Example:
        >>> from ocp_resources.pod import Pod
        >>> from tests.workbenches.utils import verify_package_import
        >>>
        >>> pod = Pod(client=client, namespace="test", name="notebook-0")
        >>> results = verify_package_import(
        ...     pod=pod,
        ...     container_name="notebook",
        ...     packages=["sdg_hub", "instructlab"]
        ... )
        >>> assert all(r.import_successful for r in results.values())
    """
    # Input validation
    if not packages:
        raise ValueError("packages list cannot be empty")

    if timeout <= 0:
        raise ValueError("timeout must be positive")

    # Validate package names (Python identifier pattern)
    package_name_pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    for package in packages:
        if not package_name_pattern.match(package):
            raise ValueError(f"Invalid package name: {package}")

    # Check pod exists and is running
    if not pod.exists:
        raise RuntimeError(f"Pod {pod.name} does not exist")

    pod_status = pod.instance.status
    if pod_status.phase != "Running":
        raise RuntimeError(f"Pod {pod.name} is not in Running state (current: {pod_status.phase})")

    # Verify container exists
    container_names = [c.name for c in pod.instance.spec.containers]
    if container_name not in container_names:
        raise RuntimeError(
            f"Container '{container_name}' not found in pod. Available containers: {container_names}"
        )

    LOGGER.info(f"Verifying {len(packages)} packages in container '{container_name}' of pod '{pod.name}'")

    # Verify each package
    results = {}
    for package_name in packages:
        command = f"python -c 'import {package_name}'"
        command_list = shlex.split(command)

        LOGGER.debug(f"Executing: {command}")

        start_time = time()
        try:
            # Execute command in container
            output = pod.execute(container=container_name, command=command_list)
            execution_time = time() - start_time

            # Success case
            results[package_name] = PackageVerificationResult(
                package_name=package_name,
                import_successful=True,
                error_message=None,
                command_executed=command,
                execution_time_seconds=execution_time,
                pod_logs=None,
                stdout=output if output else "",
                stderr="",
            )
            LOGGER.info(f"Package {package_name}: ✓ (import successful in {execution_time:.2f}s)")

        except ExecOnPodError as e:
            execution_time = time() - start_time

            # Failure case - extract error message
            error_message = str(e)
            stderr_output = error_message

            # Collect pod logs if requested
            pod_logs = None
            if collect_diagnostics:
                try:
                    pod_logs = pod.log(container=container_name, tail_lines=100)
                except Exception as log_error:
                    LOGGER.warning(f"Failed to collect pod logs: {log_error}")
                    pod_logs = "Could not retrieve pod logs"

            results[package_name] = PackageVerificationResult(
                package_name=package_name,
                import_successful=False,
                error_message=error_message,
                command_executed=command,
                execution_time_seconds=execution_time,
                pod_logs=pod_logs,
                stdout="",
                stderr=stderr_output,
            )
            LOGGER.warning(f"Package {package_name}: ✗ (import failed: {error_message})")

    return results


def get_username(dyn_client: DynamicClient) -> str | None:
    """Gets the username for the client (see kubectl -v8 auth whoami)"""
    username: str | None
    try:
        self_subject_review = SelfSubjectReview(client=dyn_client, name="selfSubjectReview").create()
        assert self_subject_review
        username = self_subject_review.status.userInfo.username
    except NotImplementedError:
        LOGGER.info(
            "SelfSubjectReview not found. Falling back to user.openshift.io/v1/users/~ for OpenShift versions <=4.14"
        )
        user = User(client=dyn_client, name="~").instance
        username = user.get("metadata", {}).get("name", None)

    return username
