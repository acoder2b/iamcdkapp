import boto3
import yaml
import logging
from datetime import datetime
from botocore.exceptions import BotoCoreError, ClientError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def list_iam_roles(exclude_paths, exclude_role_prefix):
    """
    List IAM roles in the account, excluding those with specified paths and prefixes.
    """
    iam_client = boto3.client('iam', region_name='us-east-1')
    paginator = iam_client.get_paginator('list_roles')
    roles = []

    logging.info("Listing IAM roles...")
    try:
        for page in paginator.paginate():
            for role in page['Roles']:
                role_path = role['Path']
                role_name = role['RoleName']
                if not role['Arn'].startswith('arn:aws:iam::aws:role/') and \
                   not any(role_path.startswith(path) for path in exclude_paths) and \
                   not any(role_name.startswith(prefix) for prefix in exclude_role_prefixes):
                    roles.append({
                        'RoleName': role['RoleName'],
                        'RoleArn': role['Arn']
                    })
                else:
                    logging.debug(f"Excluded role: {role_name} with path: {role_path}")

        logging.info(f"Total roles found after exclusion: {len(roles)}")
        return roles

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing IAM roles: {error}")
        return roles


def list_cf_stack_roles():
    """
    List IAM roles provisioned by CloudFormation stacks.
    """
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('describe_stacks')
    roles = []

    logging.info("Listing IAM roles from CloudFormation stacks...")
    try:
        for page in paginator.paginate():
            for stack in page['Stacks']:
                stack_name = stack['StackName']
                resources = cf_client.describe_stack_resources(StackName=stack_name)['StackResources']
                for resource in resources:
                    if resource['ResourceType'] == 'AWS::IAM::Role':
                        role_info = {
                            'StackName': stack_name,
                            'LogicalID': resource['LogicalResourceId'],
                            'PhysicalID': resource['PhysicalResourceId'],
                            'Type': resource['ResourceType'],
                            'Status': resource['ResourceStatus']
                        }
                        roles.append(role_info)
                        logging.debug(f"Found IAM Role in CFN Stack: {role_info}")

        logging.info(f"Total IAM roles in CloudFormation stacks found: {len(roles)}")
        return roles

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing CloudFormation stack roles: {error}")
        return roles


def get_iam_role_state(role_name):
    """
    Get details of an IAM role by its name.
    """
    iam_client = boto3.client('iam')
    try:
        role = iam_client.get_role(RoleName=role_name)
        return role['Role']
    except iam_client.exceptions.NoSuchEntityException:
        logging.warning(f"The role {role_name} does not exist.")
        return None
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching IAM role state for {role_name}: {error}")
        return None


def get_inline_policies(role_name):
    """
    Get inline policies attached to an IAM role.
    """
    iam_client = boto3.client('iam')
    inline_policies = {}
    try:
        policies = iam_client.list_role_policies(RoleName=role_name)['PolicyNames']
        for policy_name in policies:
            policy_document = iam_client.get_role_policy(RoleName=role_name, PolicyName=policy_name)['PolicyDocument']
            inline_policies[policy_name] = policy_document
    except Exception as e:
        logging.error(f"Error fetching inline policies for role {role_name}: {e}")

    # Return None if no inline policies are found, otherwise return the policies
    return inline_policies if inline_policies else None


def create_yaml_content(roles_data):
    """
    Create a YAML content structure from IAM role details.
    """
    yaml_content = []

    logging.info("Creating YAML content for IAM roles...")
    iam_client = boto3.client('iam')

    for role_data in roles_data:
        role_name = role_data['RoleName']
        description = role_data.get('Description')
        session_duration = role_data.get('MaxSessionDuration')
        iam_path = role_data.get('Path')
        trust_policy = role_data.get('AssumeRolePolicyDocument', {})
        tags = [{'key': tag['Key'], 'value': tag['Value']} for tag in role_data.get('Tags', [])] if 'Tags' in role_data else None

        # Get attached managed policies
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
        managed_policies = [policy['PolicyArn'] for policy in attached_policies] if attached_policies else None

        # Get inline policies
        inline_policies = get_inline_policies(role_name)

        # Get permission boundary
        permission_boundary = role_data.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn') if role_data.get('PermissionsBoundary') else None

        # Create YAML structure using dict to maintain order
        role_dict = {
            'roleName': role_name
        }

        if description:
            role_dict['description'] = description
        if session_duration:
            role_dict['sessionDuration'] = session_duration
        if iam_path:
            role_dict['iamPath'] = iam_path
        if trust_policy:
            trust_policy_statements = []
            for statement in trust_policy.get('Statement', []):
                statement_dict = {
                    'Effect': statement['Effect'],
                    'Principal': {k: (v if isinstance(v, list) else [v]) for k, v in statement['Principal'].items()},
                    'Action': statement['Action']
                }
                # Only add Condition if it exists and is not empty
                if 'Condition' in statement and statement['Condition']:
                    statement_dict['Condition'] = statement['Condition']
                trust_policy_statements.append(statement_dict)

            role_dict['trustPolicy'] = {
                'Version': trust_policy.get('Version', '2012-10-17'),
                'Statement': trust_policy_statements
            }
        if managed_policies:
            role_dict['managedPolicies'] = managed_policies
        if inline_policies:
            # Process inline policies to remove empty conditions
            processed_inline_policies = {}
            for policy_name, policy_document in inline_policies.items():
                for statement in policy_document.get('Statement', []):
                    if 'Condition' in statement and not statement['Condition']:
                        del statement['Condition']
                processed_inline_policies[policy_name] = policy_document
            role_dict['inlinePolicies'] = processed_inline_policies
        if permission_boundary:
            role_dict['permissionBoundary'] = permission_boundary
        if tags:
            role_dict['tags'] = tags

        role_dict['deletionPolicy'] = 'RETAIN'

        yaml_content.append(role_dict)

    return yaml_content


def append_to_yaml_file(new_roles_data, account_id):
    """
    Append new roles data to the existing YAML file, maintaining proper indentation and structure.
    If the file doesn't exist, create a new file with the new roles data.
    """
    yaml_file_name = f"iamrole-{account_id}.yaml"

    try:
        with open(yaml_file_name, 'r') as yaml_file:
            existing_content = yaml.safe_load(yaml_file) or {}
            logging.info(f"Loaded existing content from {yaml_file_name}.")
    except FileNotFoundError:
        existing_content = {
            'account_id': [account_id],
            'region': 'us-east-1',
            'roles': []
        }
        logging.info(f"No existing YAML file found. A new file will be created: {yaml_file_name}.")
    except yaml.YAMLError as error:
        logging.error(f"Error loading YAML file: {error}")
        return

    # Ensure 'roles' section exists
    existing_content.setdefault('roles', [])

    # Append new roles data
    existing_content['roles'].extend(new_roles_data)

    logging.info("Appending new roles to YAML file...")
    try:
        with open(yaml_file_name, 'w') as yaml_file:
            yaml.dump(existing_content, yaml_file, default_flow_style=False, sort_keys=False)
        logging.info(f"Appended new roles to YAML file {yaml_file_name} successfully.")
    except Exception as e:
        logging.error(f"Error appending to YAML file: {e}")



def get_account_id():
    """
    Get the AWS account ID of the caller.
    """
    sts_client = boto3.client('sts', region_name='us-east-1')
    try:
        identity = sts_client.get_caller_identity()
        logging.info(f"Fetched account ID: {identity['Account']}")
        return identity['Account']
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching account ID: {error}")
        return None


def main():
    logging.info("Script started...")

    exclude_paths = [
        '/aws-reserved/',
        '/aws-service-role/',
        '/service-role/',
        '/cdk-hnb'
    ]
    exclude_role_prefixes = ['cdk-hnb659fds', 'StackSet', 'AWSControlTower']

    # Get the account ID
    account_id = get_account_id()
    if not account_id:
        logging.error("Failed to retrieve account ID.")
        return

    # List all roles in the account
    roles = list_iam_roles(exclude_paths, exclude_role_prefixes)

    # List roles in CloudFormation stacks
    cf_stack_roles = list_cf_stack_roles()

    # Create a set of Role Names provisioned by CloudFormation stacks
    cf_stack_role_names = {role['PhysicalID'] for role in cf_stack_roles}
    logging.info(f"Roles provisioned by CloudFormation stacks: {cf_stack_role_names}")

    # Exclude roles that are part of CloudFormation stacks
    filtered_roles = [role for role in roles if role['RoleName'] not in cf_stack_role_names]
    logging.info(f"Roles after filtering out CloudFormation provisioned roles: {len(filtered_roles)}")

    # Fetch role details and create YAML content
    roles_data = []
    for role in filtered_roles:
        role_state = get_iam_role_state(role['RoleName'])
        if role_state:
            roles_data.append(role_state)

    if roles_data:
        logging.info(f"Roles data found: {len(roles_data)} roles to process.")
        yaml_content = create_yaml_content(roles_data)
        append_to_yaml_file(yaml_content, account_id)
    else:
        logging.warning("No valid role data found to process.")


if __name__ == "__main__":
    main()
