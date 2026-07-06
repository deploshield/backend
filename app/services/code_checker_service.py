import json
import re
from pathlib import Path


def check_env_variables(repo_path: str) -> dict:
    path = Path(repo_path)
    issues = []

    env_file = path / ".env"
    env_example = path / ".env.example"
    env_sample = path / ".env.sample"

    has_env = env_file.exists()
    has_example = env_example.exists() or env_sample.exists()

    # Find all env variables used in code
    required_vars = set()
    code_files = list(path.rglob("*.js")) + list(path.rglob("*.ts")) + list(path.rglob("*.py"))

    for f in code_files:
        if "node_modules" in str(f) or ".git" in str(f):
            continue
        try:
            content = f.read_text(errors="ignore")
            # process.env.VAR_NAME
            matches = re.findall(r'process\.env\.(\w+)', content)
            required_vars.update(matches)
            # os.environ["VAR"] or os.getenv("VAR")
            matches = re.findall(r'os\.(?:environ|getenv)\[?["\'](\w+)["\']', content)
            required_vars.update(matches)
        except Exception:
            continue

    # Check .env.example for defined vars
    example_vars = set()
    example_file = env_example if env_example.exists() else env_sample
    if example_file.exists():
        try:
            for line in example_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var = line.split("=")[0].strip()
                    example_vars.add(var)
        except Exception:
            pass

    # Find missing vars (in code but not in .env.example)
    missing_vars = required_vars - example_vars - {"NODE_ENV", "PORT", "HOST"}

    if not has_env and not has_example:
        if required_vars:
            issues.append({
                "type": "info",
                "message": f"No .env.example in repo. Code uses {len(required_vars)} env variables — make sure to provide them in the target config for deployment.",
                "variables": sorted(required_vars),
            })

    if missing_vars and has_example:
        issues.append({
            "type": "warning",
            "message": f"Variables used in code but missing from .env.example: {', '.join(sorted(missing_vars))}",
            "variables": sorted(missing_vars),
        })

    # Check if .env is committed (security issue)
    if has_env:
        gitignore = path / ".gitignore"
        env_in_gitignore = False
        if gitignore.exists():
            content = gitignore.read_text()
            if ".env" in content:
                env_in_gitignore = True

        if not env_in_gitignore:
            issues.append({
                "type": "error",
                "message": ".env file is committed to the repo and NOT in .gitignore — secrets may be exposed!",
            })

    return {
        "success": len([i for i in issues if i["type"] == "error"]) == 0,
        "env_file_found": has_env,
        "env_example_found": has_example,
        "required_variables": sorted(required_vars),
        "missing_variables": sorted(missing_vars) if missing_vars else [],
        "issues": issues,
    }


def check_dependencies(repo_path: str) -> dict:
    path = Path(repo_path)
    issues = []

    # Node.js
    pkg_file = path / "package.json"
    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text())
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})

            # Check for common missing essentials
            if "dotenv" not in deps and "dotenv" not in dev_deps:
                # Check if code uses process.env
                for f in path.rglob("*.js"):
                    if "node_modules" in str(f):
                        continue
                    try:
                        if "process.env" in f.read_text(errors="ignore"):
                            issues.append({
                                "type": "warning",
                                "message": "Code uses process.env but 'dotenv' is not in dependencies",
                            })
                            break
                    except Exception:
                        continue

            # Check for lock file
            has_lock = (path / "package-lock.json").exists() or (path / "yarn.lock").exists() or (path / "pnpm-lock.yaml").exists()
            if not has_lock:
                issues.append({
                    "type": "warning",
                    "message": "No lock file found (package-lock.json / yarn.lock / pnpm-lock.yaml). Builds may be inconsistent.",
                })

            # Check for start script
            scripts = pkg.get("scripts", {})
            if "start" not in scripts:
                issues.append({
                    "type": "warning",
                    "message": "No 'start' script in package.json",
                })

        except json.JSONDecodeError:
            issues.append({
                "type": "error",
                "message": "package.json is invalid JSON",
            })

    # Python
    req_file = path / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text()
            if not content.strip():
                issues.append({
                    "type": "warning",
                    "message": "requirements.txt is empty",
                })
        except Exception:
            pass

    return {
        "success": len([i for i in issues if i["type"] == "error"]) == 0,
        "issues": issues,
    }


def _check_js_syntax(file_path: Path, filename: str) -> list:
    """Run basic JS syntax validation by checking for unclosed strings and common errors."""
    issues = []
    try:
        content = file_path.read_text(errors="ignore")
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("*"):
                continue

            # Check for truncated/unclosed strings on a single line
            in_string = None
            escaped = False
            for ch in stripped:
                if escaped:
                    escaped = False
                    continue
                if ch == '\\':
                    escaped = True
                    continue
                if ch in ('"', "'", '`'):
                    if in_string is None:
                        in_string = ch
                    elif in_string == ch:
                        in_string = None

            # If line ends with an unclosed string and doesn't end with a continuation
            if in_string and in_string != '`' and not stripped.endswith((',', '+', '\\')):
                issues.append({
                    "type": "error",
                    "message": f"{filename}:{i}: Unclosed string literal (possible truncated code)",
                })
                break  # One is enough to flag the file

        # Bracket balance check
        open_parens = content.count("(") - content.count(")")
        open_braces = content.count("{") - content.count("}")
        open_brackets = content.count("[") - content.count("]")

        if abs(open_parens) > 2:
            issues.append({"type": "warning", "message": f"{filename}: Mismatched parentheses (could be syntax error)"})
        if abs(open_braces) > 2:
            issues.append({"type": "warning", "message": f"{filename}: Mismatched braces (could be syntax error)"})
        if abs(open_brackets) > 2:
            issues.append({"type": "warning", "message": f"{filename}: Mismatched brackets (could be syntax error)"})

    except Exception:
        pass
    return issues


def check_code_errors(repo_path: str) -> dict:
    path = Path(repo_path)
    issues = []

    # Check for syntax errors in main entry files
    entry_files = ["index.js", "app.js", "server.js", "main.js", "src/index.js", "src/app.js", "src/server.js", "main.py", "app.py"]

    for entry in entry_files:
        entry_path = path / entry
        if entry_path.exists():
            if entry.endswith(".js"):
                issues.extend(_check_js_syntax(entry_path, entry))

            try:
                content = entry_path.read_text(errors="ignore")

                # Check for require/import of non-existent local files
                local_requires = re.findall(r'require\(["\'](\./[^"\']+)["\']\)', content)
                for req in local_requires:
                    req_path = path / req
                    if not req_path.exists() and not Path(str(req_path) + ".js").exists():
                        issues.append({
                            "type": "error",
                            "message": f"{entry}: requires '{req}' but file does not exist",
                        })

            except Exception:
                continue

    return {
        "success": len([i for i in issues if i["type"] == "error"]) == 0,
        "issues": issues,
    }
