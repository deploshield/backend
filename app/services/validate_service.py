from datetime import datetime
from pathlib import Path

from app.services.git_service import clone_repository, cleanup_repository
from app.services.docker_service import check_dockerfile_exists, build_docker_image, remove_docker_image
from app.services.detector_service import detect_project_type
from app.services.dockerfile_generator import generate_dockerfile


def run_validation(repo_url: str, branch: str, deployment_id: str) -> dict:
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

    # Stage 2: Check Dockerfile exists
    dockerfile_result = check_dockerfile_exists(repo_path)

    if not dockerfile_result["success"]:
        # No Dockerfile found — auto-detect and generate
        detection = detect_project_type(repo_path)
        stages.append({
            "name": "dockerfile_check",
            "status": "generated",
            "log": f"No Dockerfile found. Detected project type: {detection['name']}",
            "detected_type": detection["type"],
            "detected_name": detection["name"],
        })

        if detection["type"] == "unknown":
            cleanup_repository(deployment_id)
            return {
                "success": False,
                "stages": stages,
                "error": "No Dockerfile found and could not detect project type. Please add a Dockerfile to your repository.",
                "completed_at": datetime.utcnow().isoformat(),
            }

        # Generate Dockerfile
        generated_dockerfile = generate_dockerfile(detection)
        if not generated_dockerfile:
            cleanup_repository(deployment_id)
            return {
                "success": False,
                "stages": stages,
                "error": f"Detected {detection['name']} but failed to generate Dockerfile template.",
                "completed_at": datetime.utcnow().isoformat(),
            }

        # Write generated Dockerfile to repo
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

    # Stage 3: Docker build
    build_result = build_docker_image(repo_path, image_tag)
    stages.append({
        "name": "docker_build",
        "status": "success" if build_result["success"] else "failed",
        "log": build_result.get("log", build_result.get("error", "")),
        "failed_step": build_result.get("failed_step"),
    })

    # Cleanup
    try:
        cleanup_repository(deployment_id)
    except Exception:
        pass
    remove_docker_image(image_tag)

    if not build_result["success"]:
        return {
            "success": False,
            "stages": stages,
            "error": build_result["error"],
            "failed_step": build_result.get("failed_step"),
            "completed_at": datetime.utcnow().isoformat(),
        }

    return {
        "success": True,
        "stages": stages,
        "message": "Build validation passed. Ready to deploy.",
        "completed_at": datetime.utcnow().isoformat(),
    }
