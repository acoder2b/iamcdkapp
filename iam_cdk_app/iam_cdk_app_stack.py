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
    def __init__(self, scope: Construct, id: str, file_path: str, account_id: str, roles: Dict[str, Any], **kwargs):
        super().__init__(scope, id, **kwargs)

        for role in roles:
            role_name = role.get('roleName')  # Use the role name directly from the YAML file
            self.create_iam_role(role)

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

        # # Use CfnRole to directly inject the trust policy JSON
        # iam_role = iam.CfnRole(
        #     self, role['roleName'],
        #     assume_role_policy_document=trust_policy,
        #     managed_policy_arns=role.get('managedPolicies', []),
        #     role_name=role['roleName'],
        #     description=role.get('description'),
        #     max_session_duration=role.get('sessionDuration', 3600),
        #     path=role.get('iamPath'),
        #     permissions_boundary=role.get('permissionBoundary'),
        #     policies=inline_policies,
        #     tags=[{"key": tag['key'], "value": tag['value']} for tag in role.get('tags', [])]
        # )

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

    def create_inline_policies(self, inline_policies_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create inline policies from the configuration."""
        inline_policies = {}

        for policy in inline_policies_config:
            if 'policyName' in policy and 'policyDocument' in policy:
                policy_document = policy['policyDocument']

                # Remove empty condition fields if present
                for statement in policy_document.get('Statement', []):
                    if 'Condition' in statement and not statement['Condition']:
                        del statement['Condition']

                inline_policies.append(
                    iam.CfnRole.PolicyProperty(
                        policy_name=policy['policyName'],
                        policy_document=policy_document
                    )
                )

        return inline_policies