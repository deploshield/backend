import subprocess
from pathlib import Path


def check_dockerfile_exists(repo_path: str) -> dict:
    dockerfile = Path(repo_path) / "Dockerfile"
    compose_file = Path(repo_path) / "docker-compose.yml"
    compose_file_alt = Path(repo_path) / "docker-compose.yaml"

    has_dockerfile = dockerfile.exists()
    has_compose = compose_file.exists() or compose_file_alt.exists()

    if not has_dockerfile and not has_compose:
        return {
            "success": False,
            "stage": "dockerfile_check",
            "error": "No Dockerfile or docker-compose.yml found in repository root",
        }

    return {
        "success": True,
        "stage": "dockerfile_check",
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "log": f"Dockerfile: {'found' if has_dockerfile else 'not found'}, docker-compose: {'found' if has_compose else 'not found'}",
    }


def build_docker_image(repo_path: str, image_tag: str) -> dict:
    try:
        result = subprocess.run(
            ["docker", "build", "-t", image_tag, "."],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            stderr_lines = result.stderr.strip().split("\n")
            failed_step = None
            error_message = result.stderr.strip()

            for line in stderr_lines:
                if "ERROR" in line or "error" in line.lower():
                    error_message = line.strip()
                    break

            for line in result.stdout.split("\n"):
                if line.startswith("Step") or line.startswith("#"):
                    failed_step = line.strip()

            return {
                "success": False,
                "stage": "docker_build",
                "error": error_message,
                "failed_step": failed_step,
                "full_log": result.stdout + "\n" + result.stderr,
            }

        return {
            "success": True,
            "stage": "docker_build",
            "image_tag": image_tag,
            "log": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stage": "docker_build",
            "error": "Docker build timed out after 600 seconds",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stage": "docker_build",
            "error": "Docker is not installed or not available in PATH",
        }
    except Exception as e:
        return {
            "success": False,
            "stage": "docker_build",
            "error": str(e),
        }


def run_container_check(image_tag: str) -> dict:
    container_name = f"{image_tag}-check"

    try:
        # Remove if exists from previous run
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)

        # Run container in background with common env vars for startup
        run_result = subprocess.run(
            ["docker", "run", "-d", "--name", container_name,
             "-e", "PORT=3000", "-e", "NODE_ENV=production",
             "-e", "HOST=0.0.0.0",
             image_tag],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if run_result.returncode != 0:
            return {
                "success": False,
                "stage": "container_start",
                "error": f"Container failed to start: {run_result.stderr.strip()}",
            }

        # Wait 10 seconds for app to start
        import time
        time.sleep(10)

        # Check if container is still running
        inspect_result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}} {{.State.ExitCode}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = inspect_result.stdout.strip()
        is_running = output.startswith("true")

        if not is_running:
            # Container crashed — get logs
            logs_result = subprocess.run(
                ["docker", "logs", "--tail", "50", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            error_logs = logs_result.stdout + logs_result.stderr

            # Cleanup
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)

            return {
                "success": False,
                "stage": "container_start",
                "error": "Container crashed after starting",
                "logs": error_logs,
            }

        # Container is running — get logs to check for errors
        logs_result = subprocess.run(
            ["docker", "logs", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        app_logs = logs_result.stdout + logs_result.stderr

        # Cleanup
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)

        return {
            "success": True,
            "stage": "container_start",
            "log": "Container started successfully",
            "app_logs": app_logs,
        }

    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
        return {
            "success": False,
            "stage": "container_start",
            "error": "Container startup check timed out",
        }
    except Exception as e:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
        return {
            "success": False,
            "stage": "container_start",
            "error": str(e),
        }


def remove_docker_image(image_tag: str):
    try:
        subprocess.run(["docker", "rmi", image_tag], capture_output=True, timeout=30)
    except Exception:
        pass
