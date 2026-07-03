TEMPLATES = {

    "react": """FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN {build_cmd}

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/build /usr/share/nginx/html 2>/dev/null || true
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",

    "node_static": """FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN {build_cmd}

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/build /usr/share/nginx/html 2>/dev/null || true
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",

    "nextjs": """FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN {build_cmd}
EXPOSE 3000
CMD ["npm", "start"]
""",

    "nuxt": """FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN {build_cmd}
EXPOSE 3000
CMD ["npm", "start"]
""",

    "nestjs": """FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN {build_cmd}
EXPOSE 3000
CMD [{start_parts}]
""",

    "express": """FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
{build_line}
EXPOSE 3000
CMD [{start_parts}]
""",

    "node": """FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
{build_line}
EXPOSE 3000
CMD [{start_parts}]
""",

    "fastapi": """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",

    "django": """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput 2>/dev/null || true
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
""",

    "python": """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt* Pipfile* pyproject.toml* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
RUN if [ -f Pipfile ]; then pip install pipenv && pipenv install --system; fi
RUN if [ -f pyproject.toml ]; then pip install .; fi
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
""",

    "java_maven": """FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
""",

    "java_gradle": """FROM gradle:8-jdk17 AS build
WORKDIR /app
COPY build.gradle* settings.gradle* ./
COPY gradle ./gradle
RUN gradle dependencies --no-daemon || true
COPY src ./src
RUN gradle build -x test --no-daemon

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
""",

    "go": """FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main .

FROM alpine:3.19
WORKDIR /app
COPY --from=build /app/main .
EXPOSE 8080
CMD ["./main"]
""",

    "rust": """FROM rust:1.77-slim AS build
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /app/target/release/app .
EXPOSE 8080
CMD ["./app"]
""",

    "php": """FROM php:8.3-apache
RUN docker-php-ext-install pdo pdo_mysql
COPY . /var/www/html/
RUN chown -R www-data:www-data /var/www/html
EXPOSE 80
CMD ["apache2-foreground"]
""",

    "static": """FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",

}


def generate_dockerfile(project_info: dict) -> str | None:
    project_type = project_info.get("type")

    if project_type == "unknown":
        return None

    template = TEMPLATES.get(project_type)
    if not template:
        return None

    build_cmd = project_info.get("build_cmd", "npm run build")
    start_cmd = project_info.get("start_cmd", "node index.js")

    # Build CMD array parts like: "node", "dist/main.js"
    start_parts = ", ".join(f'"{p}"' for p in start_cmd.split()) if start_cmd else '"node", "index.js"'

    # Build line (RUN build_cmd or empty)
    build_line = f"RUN {build_cmd}" if build_cmd else ""

    dockerfile = template.format(
        build_cmd=build_cmd,
        start_cmd=start_cmd,
        start_parts=start_parts,
        build_line=build_line,
    )

    return dockerfile
