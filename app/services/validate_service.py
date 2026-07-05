from datetime import datetime
from pathlib import Path

from app.services.git_service import clone_repository, cleanup_repository
from app.services.docker_service import check_dockerfile_exists, build_docker_image, run_container_check, remove_docker_image
from app.services.detector_service import detect_project_type
from app.services.dockerfile_generator import generate_dockerfile
from app.services.code_checker_service import check_env_variables, check_dependencies, check_code_errors


def run_validation(repo_url: str, branch: str, deployment_id: str, env_vars: str = None) -> dict:
    stages = []
    image_tag = f"deployshield-validate-{deployment_id}"

    # Stage 1: Clone repository
    clone_result = clone_repository(repo_url, branch, deployment_id)
    stages.append({
        "name": "clone",
        "status": "success" if clone_result["success"] else "failed",
        "log": clone_result.get("log", clone_result.get("error", "")),
    })

    if not clone_result["success"]:
        return {
            "success": False,
            "stages": stages,
            "error": clone_result["error"],
            "completed_at": datetime.utcnow().isoformat(),
        }

    repo_path = clone_result["path"]

    # Stage 2: Code analysis (env vars, dependencies, syntax)
    env_result = check_env_variables(repo_path)
    stages.append({
        "name": "env_check",
        "status": "success" if env_result["success"] else "warning",
        "required_variables": env_result["required_variables"],
        "missing_variables": env_result["missing_variables"],
        "issues": env_result["issues"],
        "log": f"Found {len(env_result['required_variables'])} env variables used in code"
               + (f", {len(env_result['missing_variables'])} missing from .env.example" if env_result["missing_variables"] else ""),
    })

    dep_result = check_dependencies(repo_path)
    stages.append({
        "name": "dependency_check",
        "status": "success" if dep_result["success"] else "warning",
        "issues": dep_result["issues"],
        "log": "Dependencies OK" if dep_result["success"] else f"{len(dep_result['issues'])} issue(s) found",
    })

    code_result = check_code_errors(repo_path)
    stages.append({
        "name": "code_check",
        "status": "success" if code_result["success"] else "failed",
        "issues": code_result["issues"],
        "log": "No code issues found" if code_result["success"] else f"{len(code_result['issues'])} issue(s) found",
    })

    if not code_result["success"]:
        try:
            cleanup_repository(deployment_id)
        except Exception:
            pass
        return {
            "success": False,
            "stages": stages,
            "error": "; ".join([i["message"] for i in code_result["issues"] if i["type"] == "error"]),
            "completed_at": datetime.utcnow().isoformat(),
        }

    # Stage 3: Check Dockerfile exists
    dockerfile_result = check_dockerfile_exists(repo_path)

    if not dockerfile_result["success"]:
        detection = detect_project_type(repo_path)
        stages.append({
            "name": "dockerfile_check",
            "status": "generated",
            "log": f"No Dockerfile found. Detected project type: {detection['name']}",
            "detected_type": detection["type"],
            "detected_name": detection["name"],
        })

        if detection["type"] == "unknown":
            try:
                cleanup_repository(deployment_id)
            except Exception:
                pass
            return {
                "success": False,
                "stages": stages,
                "error": "No Dockerfile found and could not detect project type. Please add a Dockerfile to your repository.",
                "completed_at": datetime.utcnow().isoformat(),
            }

        generated_dockerfile = generate_dockerfile(detection)
        if not generated_dockerfile:
            try:
                cleanup_repository(deployment_id)
            except Exception:
                pass
            return {
                "success": False,
                "stages": stages,
                "error": f"Detected {detection['name']} but failed to generate Dockerfile template.",
                "completed_at": datetime.utcnow().isoformat(),
            }

        dockerfile_path = Path(repo_path) / "Dockerfile"
        dockerfile_path.write_text(generated_dockerfile)

        stages.append({
            "name": "dockerfile_generated",
            "status": "success",
            "log": f"Generated Dockerfile for {detection['name']}",
            "generated_dockerfile": generated_dockerfile,
        })
    else:
        stages.append({
            "name": "dockerfile_check",
            "status": "success",
            "log": dockerfile_result.get("log", "Dockerfile found"),
        })

    # Stage 4: Docker build
    build_result = build_docker_image(repo_path, image_tag)
    stages.append({
        "name": "docker_build",
        "status": "success" if build_result["success"] else "failed",
        "log": build_result.get("log", build_result.get("error", "")),
        "failed_step": build_result.get("failed_step"),
    })

    if not build_result["success"]:
        try:
            cleanup_repository(deployment_id)
        except Exception:
            pass
        remove_docker_image(image_tag)
        return {
            "success": False,
            "stages": stages,
            "error": build_result["error"],
            "failed_step": build_result.get("failed_step"),
            "completed_at": datetime.utcnow().isoformat(),
        }

    # Stage 5: Container startup check
    container_result = run_container_check(image_tag, env_vars=env_vars)
    container_crashed = not container_result["success"]
    logs_text = container_result.get("app_logs", container_result.get("logs", ""))

    # Detect if crash is due to missing env vars / connection issues (not a real code bug)
    env_related_keywords = ["ECONNREFUSED", "DATABASE", "MONGO", "REDIS", "CONNECTION", "ENV", "SECRET", "undefined", "Cannot read properties of null"]
    is_env_issue = container_crashed and any(kw.lower() in (logs_text or "").lower() for kw in env_related_keywords)

    if container_crashed and is_env_issue:
        stages.append({
            "name": "container_start",
            "status": "warning",
            "log": "Container exited (likely missing env vars/database). Build is valid.",
            "app_logs": logs_text,
        })
    elif container_crashed:
        stages.append({
            "name": "container_start",
            "status": "warning",
            "log": container_result.get("error", "Container crashed after starting"),
            "app_logs": logs_text,
        })
    else:
        stages.append({
            "name": "container_start",
            "status": "success",
            "log": container_result.get("log", "Container started successfully"),
            "app_logs": logs_text,
        })

    # Cleanup
    try:
        cleanup_repository(deployment_id)
    except Exception:
        pass
    remove_docker_image(image_tag)

    # All passed (container crash is a warning, not a failure)
    all_issues = env_result["issues"] + dep_result["issues"] + code_result["issues"]
    warnings = [i for i in all_issues if i["type"] == "warning"]

    message = "All checks passed. Application builds and starts successfully."
    if container_crashed:
        message = "Build passed. Container exited during startup check (likely needs env vars/database)."

    return {
        "success": True,
        "stages": stages,
        "message": message,
        "warnings": [w["message"] for w in warnings] if warnings else [],
        "completed_at": datetime.utcnow().isoformat(),
    }
