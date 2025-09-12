#!/usr/bin/env python3
"""
Database Schema Creator with Kubernetes Secret Management

This script creates a MySQL database schema, generates a user with a random password,
grants permissions, and creates a Kubernetes Secret with the credentials.

Environment Variables Required:
- MYSQL_HOST: MySQL server hostname
- MYSQL_PORT: MySQL server port (default: 3306)
- MYSQL_ROOT_USER: MySQL root username
- MYSQL_ROOT_PASSWORD: MySQL root password
- SCHEMA_NAME: Name of the schema to create
- DB_USER: Name of the database user to create
- K8S_NAMESPACE: Kubernetes namespace for the Secret
- SECRET_NAME: Name of the Kubernetes Secret to create

Note: This script is designed to run as a pod within a Kubernetes cluster and uses
the mounted service account token for authentication.
"""

import os
import sys
import logging
import secrets
import string
import base64
import json
from typing import Optional, Dict, Any

import mysql.connector
from mysql.connector import Error
import requests
from requests.exceptions import RequestException


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseSchemaManager:
    """Manages MySQL database schema creation and user management."""
    
    def __init__(self, host: str, port: int, root_user: str, root_password: str):
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password
        self.connection = None
    
    def connect(self) -> None:
        """Establish connection to MySQL server."""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.root_user,
                password=self.root_password,
                autocommit=True
            )
            logger.info(f"Successfully connected to MySQL server at {self.host}:{self.port}")
        except Error as e:
            logger.error(f"Error connecting to MySQL: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close MySQL connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("MySQL connection closed")
    
    def create_schema(self, schema_name: str) -> None:
        """Create a new database schema."""
        try:
            cursor = self.connection.cursor()
            
            # Check if schema already exists
            cursor.execute("SHOW DATABASES LIKE %s", (schema_name,))
            if cursor.fetchone():
                logger.warning(f"Schema '{schema_name}' already exists")
                return
            
            # Create schema
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{schema_name}`")
            logger.info(f"Successfully created schema '{schema_name}'")
            
        except Error as e:
            logger.error(f"Error creating schema '{schema_name}': {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def generate_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password
    
    def create_user_and_grant_permissions(self, username: str, password: str, schema_name: str) -> None:
        """Create a new MySQL user and grant all privileges on the specified schema."""
        try:
            cursor = self.connection.cursor()
            
            # Drop user if exists (to handle recreating users)
            cursor.execute(f"DROP USER IF EXISTS '{username}'@'%'")
            
            # Create user
            cursor.execute(f"CREATE USER '{username}'@'%' IDENTIFIED BY %s", (password,))
            logger.info(f"Successfully created user '{username}'")
            
            # Grant all privileges on the schema
            cursor.execute(f"GRANT ALL PRIVILEGES ON `{schema_name}`.* TO '{username}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            logger.info(f"Successfully granted all privileges on '{schema_name}' to user '{username}'")
            
        except Error as e:
            logger.error(f"Error creating user '{username}' or granting permissions: {e}")
            raise
        finally:
            if cursor:
                cursor.close()


class KubernetesSecretManager:
    """Manages Kubernetes Secret creation via REST API."""
    
    def __init__(self):
        self.token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        self.ca_cert_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        self.namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        self.api_server_url = None
        self.token = None
        self._setup_cluster_config()
    
    def _setup_cluster_config(self) -> None:
        """Set up cluster configuration for in-cluster API access."""
        try:
            # Get Kubernetes API server URL from environment variables
            k8s_host = os.getenv('KUBERNETES_SERVICE_HOST')
            k8s_port = os.getenv('KUBERNETES_SERVICE_PORT', '443')
            
            if not k8s_host:
                raise ValueError("KUBERNETES_SERVICE_HOST environment variable not found")
            
            self.api_server_url = f"https://{k8s_host}:{k8s_port}"
            logger.info(f"Kubernetes API server URL: {self.api_server_url}")
            
            # Read service account token
            if os.path.exists(self.token_path):
                with open(self.token_path, 'r') as f:
                    self.token = f.read().strip()
                logger.info("Successfully loaded service account token")
            else:
                raise FileNotFoundError(f"Service account token not found at {self.token_path}")
                
        except Exception as e:
            logger.error(f"Error setting up cluster configuration: {e}")
            raise
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Kubernetes API requests."""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def _get_ca_cert_path(self) -> Optional[str]:
        """Get CA certificate path if it exists."""
        if os.path.exists(self.ca_cert_path):
            return self.ca_cert_path
        return None
    
    def create_secret(self, namespace: str, secret_name: str, username: str, password: str, 
                     schema_name: str, mysql_host: str, mysql_port: int) -> None:
        """Create a Kubernetes Secret with database credentials via REST API.
        
        This method will fail and exit if the Secret already exists, as overwriting
        existing credentials could cause unpredictable behavior.
        """
        try:
            # Prepare secret data (base64 encoded)
            secret_data = {
                'username': base64.b64encode(username.encode()).decode(),
                'password': base64.b64encode(password.encode()).decode(),
                'database': base64.b64encode(schema_name.encode()).decode(),
                'host': base64.b64encode(mysql_host.encode()).decode(),
                'port': base64.b64encode(str(mysql_port).encode()).decode(),
                'connection-string': base64.b64encode(
                    f"mysql://{username}:{password}@{mysql_host}:{mysql_port}/{schema_name}".encode()
                ).decode()
            }
            
            # Create Secret manifest
            secret_manifest = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": secret_name,
                    "namespace": namespace,
                    "labels": {
                        "app": "database-schema-creator",
                        "database": schema_name
                    }
                },
                "type": "Opaque",
                "data": secret_data
            }
            
            # API endpoint for secrets
            secrets_url = f"{self.api_server_url}/api/v1/namespaces/{namespace}/secrets"
            
            headers = self._get_headers()
            ca_cert = self._get_ca_cert_path()
            
            # Attempt to create the secret
            try:
                post_response = requests.post(
                    secrets_url,
                    headers=headers,
                    data=json.dumps(secret_manifest),
                    verify=ca_cert,
                    timeout=30
                )
                
                if post_response.status_code in [200, 201]:
                    logger.info(f"Successfully created Secret '{secret_name}' in namespace '{namespace}'")
                elif post_response.status_code == 409:
                    # Secret already exists - this is an error condition
                    logger.error(f"Secret '{secret_name}' already exists in namespace '{namespace}'. "
                               f"This script expects the Secret to not exist. Please investigate and "
                               f"remove the existing Secret if safe to do so, or use a different Secret name.")
                    sys.exit(1)
                else:
                    logger.error(f"Failed to create Secret: {post_response.status_code} - {post_response.text}")
                    raise RequestException(f"Failed to create Secret: {post_response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.error("Request to Kubernetes API timed out")
                raise
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error to Kubernetes API: {e}")
                raise
                
        except RequestException as e:
            logger.error(f"Error creating Kubernetes Secret: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error with Kubernetes Secret: {e}")
            raise


def get_required_env_var(var_name: str) -> str:
    """Get required environment variable or exit with error."""
    value = os.getenv(var_name)
    if not value:
        logger.error(f"Required environment variable '{var_name}' is not set")
        sys.exit(1)
    return value


def get_optional_env_var(var_name: str, default: str) -> str:
    """Get optional environment variable with default value."""
    return os.getenv(var_name, default)


def main():
    """Main execution function."""
    logger.info("Starting Database Schema Creator")
    
    # Get environment variables
    mysql_host = get_required_env_var('MYSQL_HOST')
    mysql_port = int(get_optional_env_var('MYSQL_PORT', '3306'))
    mysql_root_user = get_required_env_var('MYSQL_ROOT_USER')
    mysql_root_password = get_required_env_var('MYSQL_ROOT_PASSWORD')
    schema_name = get_required_env_var('SCHEMA_NAME')
    db_user = get_required_env_var('DB_USER')
    k8s_namespace = get_required_env_var('K8S_NAMESPACE')
    secret_name = get_required_env_var('SECRET_NAME')
    
    db_manager = None
    
    try:
        # Initialize database manager
        db_manager = DatabaseSchemaManager(
            host=mysql_host,
            port=mysql_port,
            root_user=mysql_root_user,
            root_password=mysql_root_password
        )
        
        # Connect to MySQL
        db_manager.connect()
        
        # Create schema
        logger.info(f"Creating schema '{schema_name}'")
        db_manager.create_schema(schema_name)
        
        # Generate password for new user
        user_password = db_manager.generate_password()
        logger.info(f"Generated password for user '{db_user}'")
        
        # Create user and grant permissions
        logger.info(f"Creating user '{db_user}' and granting permissions")
        db_manager.create_user_and_grant_permissions(db_user, user_password, schema_name)
        
        # Initialize Kubernetes Secret manager
        k8s_manager = KubernetesSecretManager()
        
        # Create Kubernetes Secret (will fail if Secret already exists)
        logger.info(f"Creating Kubernetes Secret '{secret_name}' in namespace '{k8s_namespace}'")
        k8s_manager.create_secret(
            namespace=k8s_namespace,
            secret_name=secret_name,
            username=db_user,
            password=user_password,
            schema_name=schema_name,
            mysql_host=mysql_host,
            mysql_port=mysql_port
        )
        
        logger.info("Database schema creation and Kubernetes Secret setup completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        sys.exit(1)
        
    finally:
        # Clean up database connection
        if db_manager:
            db_manager.disconnect()


if __name__ == "__main__":
    main()
