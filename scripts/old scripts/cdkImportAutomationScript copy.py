import boto3
import yaml
import logging
from datetime import datetime
from botocore.exceptions import BotoCoreError, ClientError


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def list_cf_stack_policies(account_id):
    """
    List IAM managed policies provisioned by CloudFormation stacks.
    Handles pagination for stack resources and fixes ARN construction.
    """
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('list_stacks')
    cf_policy_arns = []

    logging.info("Listing IAM managed policies provisioned by CloudFormation stacks...")

    try:
        for page in paginator.paginate(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE']):
            for stack_summary in page['StackSummaries']:
                stack_name = stack_summary['StackName']
                logging.info(f"Checking resources for stack: {stack_name}")
                
                # Handle pagination for stack resources
                stack_resource_paginator = cf_client.get_paginator('list_stack_resources')
                for resource_page in stack_resource_paginator.paginate(StackName=stack_name):
                    stack_resources = resource_page['StackResourceSummaries']
                    for resource in stack_resources:
                        if resource['ResourceType'] == 'AWS::IAM::ManagedPolicy':
                            physical_id = resource['PhysicalResourceId']
                            
                            # Fix ARN construction: Check if `PhysicalResourceId` is already an ARN
                            if physical_id.startswith('arn:aws:iam::'):
                                policy_arn = physical_id
                            else:
                                policy_arn = f'arn:aws:iam::{account_id}:policy/{physical_id}'
                            
                            cf_policy_arns.append(policy_arn)
                            logging.info(f"Managed Policy '{policy_arn}' is provisioned by CloudFormation stack '{stack_name}'.")
        
        logging.info(f"Total IAM managed policies in CloudFormation stacks found: {len(cf_policy_arns)}")
        return cf_policy_arns

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing CloudFormation managed policies: {error}")
        return []
    
def list_customer_managed_policies(exclude_policy_arns):
    """
    List all customer-managed IAM policies, excluding those provisioned by CloudFormation.
    """
    iam_client = boto3.client('iam', region_name='us-east-1')
    paginator = iam_client.get_paginator('list_policies')
    policies = []

    logging.info("Listing IAM customer-managed policies...")
    try:
        for page in paginator.paginate(Scope='Local'):
            for policy in page['Policies']:
                # Exclude policies provisioned by CloudFormation (based on ARNs in exclude_policy_arns)
                if policy['Arn'] not in exclude_policy_arns and '/service-role/' not in policy.get('Path', ''):
                    policies.append({
                        'PolicyName': policy['PolicyName'],
                        'PolicyArn': policy['Arn'],
                        'PolicyId': policy['PolicyId'],
                        'Path': policy.get('Path')  # Include path in case it's useful later
                    })
        logging.info(f"Total customer-managed policies found after exclusion: {len(policies)}")
        return policies

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing IAM policies: {error}")
        return []

def get_policy_tags(policy_arn):
    """Retrieve the tags for a given IAM managed policy."""
    iam_client = boto3.client('iam')
    try:
        tags = iam_client.list_policy_tags(PolicyArn=policy_arn)['Tags']
        return [{'key': tag['Key'], 'value': tag['Value']} for tag in tags]
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching tags for policy {policy_arn}: {error}")
        return []

def get_policy_details(policy_arn):
    """
    Get details of a customer-managed IAM policy by its ARN, including description and tags.
    """

    iam_client = boto3.client('iam')
    try:
        policy = iam_client.get_policy(PolicyArn=policy_arn)['Policy']
        policy_version = iam_client.get_policy_version(
            PolicyArn=policy_arn,
            VersionId=policy['DefaultVersionId']
        )['PolicyVersion']['Document']
        
        tags = iam_client.list_policy_tags(PolicyArn=policy_arn).get('Tags', [])
        
        return {
            'PolicyName': policy['PolicyName'],
            'Description': policy.get('Description'),
            'Path': policy.get('Path'),
            'PolicyDocument': policy_version,
            'Tags': tags
        }
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching IAM policy details for {policy_arn}: {error}")
        return None

def list_iam_roles(exclude_paths, exclude_role_prefixes):
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
                
                # Exclude roles based on paths and prefixes
                if any(role_path.startswith(path) for path in exclude_paths):
                    logging.debug(f"Excluded role by path: {role_name} with path: {role_path}")
                    continue
                
                if any(role_name.startswith(prefix) for prefix in exclude_role_prefixes):
                    logging.debug(f"Excluded role by prefix: {role_name}")
                    continue

                # Add valid roles
                roles.append({
                    'RoleName': role['RoleName'],
                    'RoleArn': role['Arn']
                })

        logging.info(f"Total roles found after exclusion: {len(roles)}")
        return roles

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing IAM roles: {error}")
        return roles

def filter_policies(policies, cf_policy_arns):
    """
    Filter out policies provisioned by CloudFormation.
    """
    filtered_policies = [policy for policy in policies if policy['PolicyArn'] not in cf_policy_arns]
    logging.info(f"Total customer-managed policies after filtering CloudFormation provisioned ones: {len(filtered_policies)}")
    return filtered_policies

def list_cf_stack_roles():
    """
    List IAM roles provisioned by CloudFormation stacks and log their stack names.
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
                        roles.append(resource['PhysicalResourceId'])
                        logging.info(f"Role '{resource['PhysicalResourceId']}' is provisioned by CloudFormation stack '{stack_name}'.")

        logging.info(f"Total IAM roles in CloudFormation stacks found: {len(roles)}")
        return roles

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing CloudFormation stack roles: {error}")
        return []
    
# def get_iam_role_state(role_name):
#     iam_client = boto3.client('iam')
#     try:
#         role = iam_client.get_role(RoleName=role_name)['Role']
        
#         # Fetch attached managed policies
#         attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
#         role['ManagedPolicies'] = [{'PolicyName': policy['PolicyName'], 'PolicyArn': policy['PolicyArn']} for policy in attached_policies]
        
#         # Fetch inline policies
#         role['InlinePolicies'] = get_inline_policies(role_name)
        
#         return role
#     except iam_client.exceptions.NoSuchEntityException:
#         logging.warning(f"The role {role_name} does not exist.")
#         return None
#     except (BotoCoreError, ClientError) as error:
#         logging.error(f"Error fetching IAM role state for {role_name}: {error}")
#         return None

# def get_iam_role_state(role_name):
#     """
#     Get details of an IAM role by its name.
#     """
#     iam_client = boto3.client('iam')
#     try:
#         role = iam_client.get_role(RoleName=role_name)
#         return role['Role']
#     except iam_client.exceptions.NoSuchEntityException:
#         logging.warning(f"The role {role_name} does not exist.")
#         return None
#     except (BotoCoreError, ClientError) as error:
#         logging.error(f"Error fetching IAM role state for {role_name}: {error}")
#         return None

def get_iam_role_state(role_name):
    """
    Get details of an IAM role by its name, including permission boundary if it exists.
    """
    iam_client = boto3.client('iam')
    try:
        role = iam_client.get_role(RoleName=role_name)['Role']
        
        # Retrieve permission boundary if it exists
        if 'PermissionsBoundary' in role:
            role['PermissionBoundary'] = role['PermissionsBoundary']['PermissionsBoundaryArn']
        
        return role
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

def create_yaml_content(policies, roles):
    """
    Create a YAML content structure for both IAM managed policies and IAM roles with proper indentation.
    """
    yaml_content = {'iam_policies': [], 'iam_roles': []}

    logging.info("Creating YAML content for IAM policies and roles...")

    # Process policies
    for policy in policies:
        policy_dict = {
            'policyName': policy['PolicyName'],
            'deletionPolicy': 'RETAIN'
        }
        if policy.get('PolicyDocument'):
            policy_dict['policyDocument'] = policy['PolicyDocument']
        if policy.get('Description'):
            policy_dict['description'] = policy['Description']
        if policy.get('Path'):
            policy_dict['path'] = policy['Path']
        if policy.get('Tags'):
            policy_dict['tags'] = [{'Key': tag['Key'], 'Value': tag['Value']} for tag in policy['Tags']]

        yaml_content['iam_policies'].append(policy_dict)

    # Process roles
    for role in roles:
        role_dict = {
            'roleName': role['RoleName'],
            'deletionPolicy': 'RETAIN'
        }

        if role.get('Description'):
            role_dict['description'] = role['Description']
        if role.get('MaxSessionDuration'):
            role_dict['sessionDuration'] = role['MaxSessionDuration']
        if role.get('Path'):
            role_dict['iamPath'] = role['Path']
        if role.get('AssumeRolePolicyDocument'):
            role_dict['trustPolicy'] = role['AssumeRolePolicyDocument']
        if role.get('Tags'):
            role_dict['tags'] = [{'key': tag['Key'], 'value': tag['Value']} for tag in role.get('Tags', [])]

        # Include permission boundary if it exists
        # Extract only the PermissionsBoundaryArn if PermissionsBoundary exists
        if role.get('PermissionsBoundary') and role['PermissionsBoundary'].get('PermissionsBoundaryArn'):
            role_dict['permissionsBoundary'] = role['PermissionsBoundary']['PermissionsBoundaryArn']


        # Attach managed policies and inline policies, if present
        if role.get('ManagedPolicies'):
            role_dict['managedPolicies'] = [policy['PolicyArn'] for policy in role['ManagedPolicies']]
        if role.get('InlinePolicies'):
            role_dict['inlinePolicies'] = role['InlinePolicies']

        yaml_content['iam_roles'].append(role_dict)

    return yaml_content



def build_full_yaml_structure(account_id, region, roles_data, policies_data):
    """
    Build a complete ordered YAML structure including account and policy information.
    """
    # Pass both policies and roles to create_yaml_content
    yaml_content = create_yaml_content(policies_data, roles_data)
    
    yaml_structure = {
        'account_id': [account_id],
        'region': region,
        'stack_name': 'iam-role-policies-pipeline-stack',
        'iam_policies': yaml_content['iam_policies'],
        'roles': yaml_content['iam_roles']
    }

    return yaml_structure


def append_to_yaml_file(full_yaml_structure, account_id):
    """
    Write the ordered YAML content to a file.
    """
    yaml_file_name = f"iamrole-policies-{account_id}.yaml"

    # try:
    #     with open(yaml_file_name, 'w') as yaml_file:
    #         yaml.dump(full_yaml_structure, yaml_file, default_flow_style=False, sort_keys=False, indent=4)
    #     logging.info(f"YAML file {yaml_file_name} created successfully.")
    # except Exception as e:
    #     logging.error(f"Error writing to YAML file: {e}")
    try:
        with open(yaml_file_name, 'w') as yaml_file:
            yaml.dump(
                full_yaml_structure, 
                yaml_file, 
                default_flow_style=False,  # Ensures the output is not compacted, and follows a block style
                sort_keys=False,           # Keeps the keys in the same order as provided
                indent=4                   # Ensures proper indentation for nested structures
            )
        logging.info(f"YAML file {yaml_file_name} created successfully.")
    except Exception as e:
        logging.error(f"Error writing to YAML file: {e}")    

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

    exclude_paths = ['/aws-reserved/', '/aws-service-role/', '/service-role/', '/cdk-hnb']
    exclude_role_prefixes = ['cdk-hnb659fds', 'StackSet', 'stackset', 'AWSControlTower']
    account_id = get_account_id()
    region = 'us-east-1'

    if not account_id:
        logging.error("Failed to retrieve account ID.")
        return

    # Step 1: List all roles in the account
    roles = list_iam_roles(exclude_paths, exclude_role_prefixes)

    # Step 2: List roles in CloudFormation stacks
    cf_stack_roles = list_cf_stack_roles()
    cf_stack_role_names = set(cf_stack_roles)

    # Handle case where `cf_stack_roles` may not be in expected format
    if isinstance(cf_stack_roles, list) and all(isinstance(role, dict) and 'PhysicalID' in role for role in cf_stack_roles):
        cf_stack_role_names = {role['PhysicalID'] for role in cf_stack_roles}
    else:
        cf_stack_role_names = set(cf_stack_roles)  # Assuming it may just be a list of role names

    logging.info(f"Roles provisioned by CloudFormation stacks: {cf_stack_role_names}")

    # Step 3: Exclude roles that are part of CloudFormation stacks
    filtered_roles = [role for role in roles if role['RoleName'] not in cf_stack_role_names]
    logging.info(f"Roles after filtering out CloudFormation provisioned roles: {len(filtered_roles)}")

    # Step 4: Fetch role details, including managed and inline policies, for each filtered role
    roles_data = []
    iam_client = boto3.client('iam', region_name='us-east-1')
    for role in filtered_roles:
        role_state = get_iam_role_state(role['RoleName'])
        if role_state:
            # Fetch managed policies attached to the role
            attached_policies = iam_client.list_attached_role_policies(RoleName=role['RoleName'])['AttachedPolicies']
            role_state['ManagedPolicies'] = [{'PolicyName': policy['PolicyName'], 'PolicyArn': policy['PolicyArn']} for policy in attached_policies]

            # Fetch inline policies
            role_state['InlinePolicies'] = get_inline_policies(role['RoleName'])

            roles_data.append(role_state)

    # Step 5: List IAM policies provisioned by CloudFormation stacks
    cf_stack_policy_arns = list_cf_stack_policies(account_id)

    # Step 6: List all customer-managed policies excluding CloudFormation-managed ones
    customer_managed_policies = list_customer_managed_policies(cf_stack_policy_arns)
    policies_data = []
    for policy in customer_managed_policies:
        policy_details = get_policy_details(policy['PolicyArn'])
        if policy_details:
            policies_data.append(policy_details)  # Store all details returned by get_policy_details

    # Step 8: Build full YAML structure
    full_yaml_structure = build_full_yaml_structure(account_id, region, roles_data, policies_data)

    # Step 9: Append the data to the YAML file
    append_to_yaml_file(full_yaml_structure, account_id)

if __name__ == "__main__":
    main()

