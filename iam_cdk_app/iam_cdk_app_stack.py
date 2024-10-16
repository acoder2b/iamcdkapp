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
    def __init__(self, scope: Construct, id: str, file_path: str, account_id: str, resources: Dict[str, Any], **kwargs):
        super().__init__(scope, id, **kwargs)

        roles = resources.get("roles", [])
        for role in roles:
            self.create_iam_role(role)

        # Process and create custom managed policies
        managed_policies = resources.get("iam_policies", [])
        for policy in managed_policies:
            self.create_managed_policy(policy)

    def create_managed_policy(self, policy_config: Dict[str, Any]) -> None:
        """Create a custom managed IAM policy based on the provided configuration."""
        policy_name = policy_config.get('policyName')
        policy_document = policy_config.get('policyDocument', {})

        # Create the IAM managed policy
        iam_policy = iam.CfnManagedPolicy(
            self,
            id=f"{policy_name}-ManagedPolicy",
            managed_policy_name=policy_name,
            policy_document=policy_document,
        )

        logger.info(f"Created IAM managed policy {policy_name}")

    def create_iam_role(self, role: Dict[str, Any]) -> None:
        """Create an IAM role based on the provided configuration."""
        trust_policy = role.get('trustPolicy', {})
        inline_policies = self.create_inline_policies(role.get('inlinePolicies', {}))

        if inline_policies:
            logger.info(f"Adding inline policies for role: {role['roleName']}")
        else:
            logger.warning(f"No inline policies found for role: {role['roleName']}")

        # Create the role's properties dynamically, avoiding empty lists or unnecessary fields
        role_properties = {
            'assume_role_policy_document': trust_policy,
            'role_name': role['roleName']
        }

        # Conditionally add properties if they are set
        if 'description' in role:
            role_properties['description'] = role['description']
        if 'sessionDuration' in role:
            role_properties['max_session_duration'] = role['sessionDuration']
        if 'iamPath' in role:
            role_properties['path'] = role['iamPath']
        if 'permissionsBoundary' in role:
            role_properties['permissions_boundary'] = role['permissionsBoundary']
        if 'managedPolicies' in role and role['managedPolicies']:
            role_properties['managed_policy_arns'] = role['managedPolicies']
        if inline_policies:
            role_properties['policies'] = inline_policies
        if 'tags' in role and role['tags']:
            role_properties['tags'] = [{"key": tag['key'], "value": tag['value']} for tag in role['tags']]

        # Use CfnRole to directly inject the trust policy JSON
        iam_role = iam.CfnRole(
            self, role['roleName'],
            **role_properties
        )
        # Set the DeletionPolicy to RETAIN if specified in the YAML configuration
        if role.get('deletionPolicy') == 'RETAIN':
            iam_role.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN

        logger.info(f"Created IAM role {role['roleName']} with direct JSON trust policy.")

    def create_inline_policies(self, inline_policies_config: Dict[str, Any]) -> List[iam.CfnRole.PolicyProperty]:
        """Create inline policies from the configuration."""
        inline_policies = []

        # Ensure inline_policies_config is a dictionary
        if isinstance(inline_policies_config, dict):
            for policy_name, policy_document in inline_policies_config.items():
                logger.info(f"Processing inline policy: {policy_name}")
                
                if policy_document:
                    # Remove empty condition fields if present
                    for statement in policy_document.get('Statement', []):
                        if 'Condition' in statement and not statement['Condition']:
                            del statement['Condition']

                    # Append each policy as a CfnRole.PolicyProperty
                    inline_policies.append(
                        iam.CfnRole.PolicyProperty(
                            policy_name=policy_name,
                            policy_document=policy_document
                        )
                    )
                else:
                    logger.warning(f"Policy document for {policy_name} is empty or invalid.")
        else:
            logger.error("inlinePolicies config is not a dictionary. Please check your YAML format.")

        return inline_policies

