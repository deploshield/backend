from pathlib import Path


def detect_project_type(repo_path: str) -> dict:
    path = Path(repo_path)
    files = [f.name for f in path.iterdir() if f.is_file()]

    # Node.js
    if "package.json" in files:
        import json
        pkg = json.loads((path / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        scripts = pkg.get("scripts", {})

        if "next" in deps:
            return {"type": "nextjs", "name": "Next.js", "build_cmd": scripts.get("build", "npm run build"), "start_cmd": "npm start", "port": 3000}
        if "nuxt" in deps:
            return {"type": "nuxt", "name": "Nuxt", "build_cmd": scripts.get("build", "npm run build"), "start_cmd": "npm start", "port": 3000}
        if "react-scripts" in deps or "vite" in deps or "@vitejs/plugin-react" in deps:
            return {"type": "react", "name": "React (Static)", "build_cmd": scripts.get("build", "npm run build"), "start_cmd": None, "port": 80}
        if "@nestjs/core" in deps:
            return {"type": "nestjs", "name": "NestJS", "build_cmd": scripts.get("build", "npm run build"), "start_cmd": scripts.get("start:prod", "node dist/main.js"), "port": 3000}
        if "express" in deps:
            return {"type": "express", "name": "Express.js", "build_cmd": scripts.get("build"), "start_cmd": scripts.get("start", "node index.js"), "port": 3000}

        if "build" in scripts:
            return {"type": "node_static", "name": "Node.js (Static Build)", "build_cmd": scripts["build"], "start_cmd": None, "port": 80}

        return {"type": "node", "name": "Node.js", "build_cmd": scripts.get("build"), "start_cmd": scripts.get("start", "node index.js"), "port": 3000}

    # Python
    if "requirements.txt" in files or "Pipfile" in files or "pyproject.toml" in files:
        if "manage.py" in files:
            return {"type": "django", "name": "Django", "port": 8000}
        if (path / "app").is_dir() or "main.py" in files:
            return {"type": "fastapi", "name": "FastAPI", "port": 8000}
        return {"type": "python", "name": "Python", "port": 8000}

    # Java
    if "pom.xml" in files:
        return {"type": "java_maven", "name": "Java (Maven)", "port": 8080}
    if "build.gradle" in files or "build.gradle.kts" in files:
        return {"type": "java_gradle", "name": "Java (Gradle)", "port": 8080}

    # Go
    if "go.mod" in files:
        return {"type": "go", "name": "Go", "port": 8080}

    # Rust
    if "Cargo.toml" in files:
        return {"type": "rust", "name": "Rust", "port": 8080}

    # PHP
    if "composer.json" in files:
        return {"type": "php", "name": "PHP", "port": 80}

    # Static HTML
    if "index.html" in files:
        return {"type": "static", "name": "Static HTML", "port": 80}

    return {"type": "unknown", "name": "Unknown"}
