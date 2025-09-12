# Database Schema Creator

A Python script that automates the creation of MySQL database schemas, user management, and Kubernetes Secret generation for database credentials.

## Features

- **MySQL Schema Creation**: Creates a new database schema if it doesn't exist
- **User Management**: Generates secure random passwords and creates MySQL users with full access to the schema
- **Kubernetes Integration**: Creates Kubernetes Secrets with database credentials (fails if Secret already exists)
- **Comprehensive Logging**: Detailed logging for monitoring and debugging
- **Error Handling**: Robust error handling with proper cleanup
- **Fail-Fast Approach**: Exits with error code 1 if Secret already exists to prevent accidental overwrites
- **Multi-Architecture Docker Image**: Supports both AMD64 and ARM64 architectures

## Prerequisites

- Python 3.7+ (if running locally) or Docker/Kubernetes (for containerized deployment)
- MySQL server access with root privileges
- Kubernetes cluster access with appropriate Service Account permissions
- Designed to run as a pod within the Kubernetes cluster (uses mounted service account token)

## Installation

### Option 1: Docker (Recommended)
```bash
docker pull ghcr.io/colin-lacy/sveltos-nats-workflows/knapscen-create-database:latest
```

### Option 2: Local Python
1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Docker Usage
```bash
docker run --rm \
  -e MYSQL_HOST="your-mysql-host" \
  -e MYSQL_ROOT_USER="root" \
  -e MYSQL_ROOT_PASSWORD="your-root-password" \
  -e SCHEMA_NAME="my_application_db" \
  -e DB_USER="app_user" \
  -e K8S_NAMESPACE="default" \
  -e SECRET_NAME="db-credentials" \
  ghcr.io/colin-lacy/sveltos-nats-workflows/knapscen-create-database:latest
```

### Local Python Usage
Set the required environment variables and run the script:

```bash
export MYSQL_HOST="your-mysql-host"
export MYSQL_ROOT_USER="root"
export MYSQL_ROOT_PASSWORD="your-root-password"
export SCHEMA_NAME="my_application_db"
export DB_USER="app_user"
export K8S_NAMESPACE="default"
export SECRET_NAME="db-credentials"

python create_database_schema.py
```

## Dependencies

The script uses two main libraries:
- `mysql-connector-python` - For MySQL database operations  
- `requests` - For HTTP requests to the Kubernetes REST API

## Environment Variables

### Required Variables

| Variable | Description |
|----------|-------------|
| `MYSQL_HOST` | MySQL server hostname or IP address |
| `MYSQL_ROOT_USER` | MySQL root username |
| `MYSQL_ROOT_PASSWORD` | MySQL root password |
| `SCHEMA_NAME` | Name of the database schema to create |
| `DB_USER` | Name of the database user to create |
| `K8S_NAMESPACE` | Kubernetes namespace for the Secret |
| `SECRET_NAME` | Name of the Kubernetes Secret to create |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_PORT` | MySQL server port | `3306` |

## Kubernetes Secret Structure

The created Secret will contain the following base64-encoded data:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <SECRET_NAME>
  namespace: <K8S_NAMESPACE>
  labels:
    app: database-schema-creator
    database: <SCHEMA_NAME>
type: Opaque
data:
  username: <base64-encoded-username>
  password: <base64-encoded-password>
  database: <base64-encoded-schema-name>
```

## Security Features

- **Secure Password Generation**: Uses Python's `secrets` module for cryptographically secure random password generation
- **Base64 Encoding**: All sensitive data in Kubernetes Secrets is properly base64 encoded
- **User Isolation**: Each database user is granted permissions only to their specific schema
- **Service Account Authentication**: Uses mounted service account token for secure Kubernetes API access
- **TLS Verification**: Verifies Kubernetes API server TLS certificates using mounted CA certificate
- **Non-Root Container**: Docker image runs as non-root user for enhanced security

## Error Handling

The script includes comprehensive error handling for:
- MySQL connection failures
- Database/user creation errors
- Kubernetes API errors
- Missing environment variables
- Secret already exists (exits with code 1)
- Network connectivity issues

## Docker Image

The project is packaged as a multi-architecture Docker image available at:
- **Registry**: `ghcr.io/colin-lacy/sveltos-nats-workflows/knapscen-create-database`
- **Architectures**: `linux/amd64`, `linux/arm64`
- **Tags**: 
  - `latest` - Latest stable build from main branch
  - `main-YYYYMMDD-<commit-sha>` - Incremental builds from main
  - `v1.0.0` - Tagged semantic versions

### Building Locally
```bash
docker build -t database-schema-creator .
```

## Kubernetes Deployment

See `k8s-deployment-example.yaml` for a complete example of how to deploy this script as a Kubernetes Job with the necessary Service Account permissions. The example includes:

- Service Account with Secret management permissions
- Role and RoleBinding for RBAC
- Job specification with environment variables using the containerized image

## Service Account Permissions

The script requires the following Kubernetes RBAC permissions:
- `create` on `secrets` in the target namespace

Note: The script will fail and exit with code 1 if the Secret already exists, rather than overwriting it.

## Example Usage in CI/CD

```bash
#!/bin/bash
# Set environment variables
export MYSQL_HOST="mysql.example.com"
export MYSQL_ROOT_USER="root"
export MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD}"
export SCHEMA_NAME="myapp_${ENVIRONMENT}"
export DB_USER="myapp_user_${ENVIRONMENT}"
export K8S_NAMESPACE="${ENVIRONMENT}"
export SECRET_NAME="myapp-db-credentials"

# Run using Docker
docker run --rm \
  -e MYSQL_HOST \
  -e MYSQL_ROOT_USER \
  -e MYSQL_ROOT_PASSWORD \
  -e SCHEMA_NAME \
  -e DB_USER \
  -e K8S_NAMESPACE \
  -e SECRET_NAME \
  ghcr.io/colin-lacy/sveltos-nats-workflows/knapscen-create-database:latest

# Verify the secret was created
kubectl get secret myapp-db-credentials -n ${ENVIRONMENT}
```

## GitHub Actions

The project includes a GitHub Actions workflow (`.github/workflows/build-image.yaml`) that automatically:
- Builds multi-architecture Docker images (AMD64 and ARM64)
- Tags images incrementally with build numbers and semantic versions
- Pushes images to GitHub Container Registry
- Runs on pushes to main branch and tagged releases

## License

MIT License - see LICENSE file for details.