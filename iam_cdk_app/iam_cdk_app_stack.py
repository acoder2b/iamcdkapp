import logging
from typing import List, Dict, Any
from aws_cdk import (
    aws_iam as iam,
    Duration,
    Tags,
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
        for role in config.get('roles', []):
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

        if 'Statement' not in trust_policy or not isinstance(trust_policy['Statement'], list):
            raise ValueError(f"Statement should be a list for role {role['roleName']}")

        assume_role_policy_statements = self.create_assume_role_policy_statements(trust_policy, role.get('externalIds', []))
        assume_role_policy_doc = iam.PolicyDocument(statements=assume_role_policy_statements)

        managed_policies = [
            iam.ManagedPolicy.from_managed_policy_arn(self, f"ManagedPolicy{role['roleName']}{mp}", mp)
            for mp in role.get('managedPolicies', [])
        ]

        inline_policies = self.create_inline_policies(role.get('inlinePolicies', []))

        permissions_boundary = None
        if 'permissionBoundary' in role:
            permissions_boundary = iam.ManagedPolicy.from_managed_policy_arn(
                self, f"BoundaryPolicy{role['roleName']}", role['permissionBoundary']
            )

        # Flatten the list of principals for the CompositePrincipal
        principals = [principal for stmt in assume_role_policy_statements for principal in stmt.principals]

        iam_role = iam.Role(
            self, role['roleName'],
            assumed_by=iam.CompositePrincipal(*principals),
            managed_policies=managed_policies,
            inline_policies=inline_policies if inline_policies else None,
            role_name=role['roleName'],
            description=role.get('description'),
            max_session_duration=Duration.seconds(role.get('sessionDuration', 3600)),
            path=role.get('iamPath'),
            permissions_boundary=permissions_boundary
        )

        if 'tags' in role:
            for tag in role['tags']:
                Tags.of(iam_role).add(tag['key'], tag['value'])

        logger.info(f"Created IAM role {role['roleName']}")

    def create_assume_role_policy_statements(self, trust_policy: Dict[str, Any], external_ids: List[str]) -> List[iam.PolicyStatement]:
        """Create assume role policy statements from the trust policy configuration."""
        assume_role_policy_statements = []

        for statement in trust_policy['Statement']:
            principals = self.get_principals_from_statement(statement)
            conditions = statement.get('Condition', {})

            if external_ids:
                if 'StringEquals' not in conditions:
                    conditions['StringEquals'] = {}
                conditions['StringEquals']['sts:ExternalId'] = external_ids

            assume_role_policy_statement = iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                principals=principals,
                conditions=conditions or None,
                effect=iam.Effect.ALLOW
            )

            assume_role_policy_statements.append(assume_role_policy_statement)

        return assume_role_policy_statements

    def get_principals_from_statement(self, statement: Dict[str, Any]) -> List[iam.PrincipalBase]:
        """Extract principals from the statement."""
        principals = []
        if 'Principal' in statement:
            principal_section = statement['Principal']

            if 'Service' in principal_section:
                service_principals = principal_section['Service']
                if isinstance(service_principals, str):
                    service_principals = [service_principals]
                principals.extend([iam.ServicePrincipal(sp) for sp in service_principals])

            if 'AWS' in principal_section:
                aws_principals = principal_section['AWS']
                if isinstance(aws_principals, (str, int)):
                    aws_principals = [str(aws_principals)]
                else:
                    aws_principals = [str(arn) for arn in aws_principals]
                for arn in aws_principals:
                    if arn.isdigit():  # Check if the string is a digit (account number)
                        principals.append(iam.ArnPrincipal(f"arn:aws:iam::{arn}:root"))
                    else:
                        principals.append(iam.ArnPrincipal(arn))

        return principals

    def create_inline_policies(self, inline_policies_config: List[Dict[str, Any]]) -> Dict[str, iam.PolicyDocument]:
        """Create inline policies from the configuration."""
        inline_policies = {}

        for policy in inline_policies_config:
            if 'policyName' in policy and 'policyDocument' in policy:
                statements = [
                    iam.PolicyStatement(
                        actions=stmt['Action'] if isinstance(stmt['Action'], list) else [stmt['Action']],
                        resources=stmt['Resource'] if isinstance(stmt['Resource'], list) else [stmt['Resource']],
                        effect=iam.Effect.ALLOW,
                    ) for stmt in policy['policyDocument']['Statement']
                    if 'Action' in stmt and 'Resource' in stmt and 'Principal' not in stmt
                ]
                inline_policies[policy['policyName']] = iam.PolicyDocument(statements=statements)

        return inline_policies
