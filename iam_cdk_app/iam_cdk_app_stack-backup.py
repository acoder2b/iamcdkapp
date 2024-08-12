import logging
from typing import List, Dict, Any
from aws_cdk import CfnDeletionPolicy
from aws_cdk import (
    aws_iam as iam,
    Stack
)
from constructs import Construct
import yaml

# Configure logging
logger = logging.getLogger(__name__)

class IamRoleConfigStack(Stack):
    def __init__(self, scope: Construct, id: str, file_path: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        config = self.load_yaml_config(file_path)
        roles = config.get('roles', [])
        if not isinstance(roles, list):
            roles = []

        for role in roles:
            self.create_iam_role(role)

    def load_yaml_config(self, file_path: str) -> Dict[str, Any]:
        """Load and parse the YAML configuration file."""
        try:
            with open(file_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Loaded configuration from {file_path}")
                return config
        except FileNotFoundError:
            logger.error(f"Configuration file {file_path} not found.")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {file_path}: {e}")
            raise

    def create_iam_role(self, role: Dict[str, Any]) -> None:
        """Create an IAM role based on the provided configuration."""
        trust_policy = role.get('trustPolicy', {})

        # Handle inline policies
        inline_policies = [
            iam.CfnRole.PolicyProperty(
                policy_name=name,
                policy_document=doc
            )
            for name, doc in self.create_inline_policies(role.get('inlinePolicies', [])).items()
        ]

        # Use CfnRole to directly inject the trust policy JSON
        iam_role = iam.CfnRole(
            self, role['roleName'],
            assume_role_policy_document=trust_policy,
            managed_policy_arns=role.get('managedPolicies', []),
            role_name=role['roleName'],
            description=role.get('description'),
            max_session_duration=role.get('sessionDuration', 3600),
            path=role.get('iamPath'),
            permissions_boundary=role.get('permissionBoundary'),
            policies=inline_policies,
            tags=[{"key": tag['key'], "value": tag['value']} for tag in role.get('tags', [])]
        )

        # Set the DeletionPolicy to RETAIN if specified in the YAML configuration
        if role.get('deletionPolicy') == 'RETAIN':
            iam_role.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN

        logger.info(f"Created IAM role {role['roleName']} with direct JSON trust policy.")

    def create_inline_policies(self, inline_policies_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create inline policies from the configuration."""
        inline_policies = {}

        for policy in inline_policies_config:
            if 'policyName' in policy and 'policyDocument' in policy:
                inline_policies[policy['policyName']] = policy['policyDocument']

        return inline_policies
