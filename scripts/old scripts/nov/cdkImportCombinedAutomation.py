
import boto3
import logging
import yaml
from botocore.exceptions import BotoCoreError, ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common function to get AWS account ID
def get_account_id():
    sts_client = boto3.client('sts')
    try:
        identity = sts_client.get_caller_identity()
        logging.info(f"Fetched account ID: {identity['Account']}")
        return identity['Account']
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching account ID: {error}")
        return None

# Role automation logic
def list_iam_roles(exclude_paths, exclude_role_prefixes):
    iam_client = boto3.client('iam')
    roles = []
    paginator = iam_client.get_paginator('list_roles')

    logging.info("Listing IAM roles...")
    for page in paginator.paginate():
        for role in page['Roles']:
            # Exclude roles based on path and prefix
            if any(role['Path'].startswith(path) for path in exclude_paths) or                any(role['RoleName'].startswith(prefix) for prefix in exclude_role_prefixes):
                continue
            roles.append(role)
    logging.info(f"Total roles fetched: {len(roles)}")
    return roles

def list_cf_stack_roles():
    cf_client = boto3.client('cloudformation')
    paginator = cf_client.get_paginator('list_stacks')
    cf_role_arns = []

    logging.info("Listing IAM roles provisioned by CloudFormation stacks...")
    for page in paginator.paginate(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE']):
        for stack_summary in page['StackSummaries']:
            stack_name = stack_summary['StackName']
            logging.info(f"Checking resources for stack: {stack_name}")

            stack_resource_paginator = cf_client.get_paginator('list_stack_resources')
            for resource_page in stack_resource_paginator.paginate(StackName=stack_name):
                stack_resources = resource_page['StackResourceSummaries']
                for resource in stack_resources:
                    if resource['ResourceType'] == 'AWS::IAM::Role':
                        cf_role_arns.append(resource['PhysicalResourceId'])
    return cf_role_arns

# Policy automation logic
def list_cf_stack_policies(account_id):
    cf_client = boto3.client('cloudformation')
    paginator = cf_client.get_paginator('list_stacks')
    cf_policy_arns = []

    logging.info("Listing IAM managed policies provisioned by CloudFormation stacks...")
    for page in paginator.paginate(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE']):
        for stack_summary in page['StackSummaries']:
            stack_name = stack_summary['StackName']
            logging.info(f"Checking resources for stack: {stack_name}")

            stack_resource_paginator = cf_client.get_paginator('list_stack_resources')
            for resource_page in stack_resource_paginator.paginate(StackName=stack_name):
                stack_resources = resource_page['StackResourceSummaries']
                for resource in stack_resources:
                    if resource['ResourceType'] == 'AWS::IAM::ManagedPolicy':
                        physical_id = resource['PhysicalResourceId']
                        policy_arn = f'arn:aws:iam::{account_id}:policy/{physical_id}' if not physical_id.startswith('arn:aws:iam::') else physical_id
                        cf_policy_arns.append(policy_arn)
                        logging.info(f"Managed Policy '{policy_arn}' is provisioned by CloudFormation stack '{stack_name}'.")
    return cf_policy_arns

def list_iam_managed_policies():
    iam_client = boto3.client('iam')
    paginator = iam_client.get_paginator('list_policies')
    policies = []

    logging.info("Listing IAM managed policies...")
    for page in paginator.paginate(Scope='Local'):
        policies.extend(page['Policies'])
    logging.info(f"Total policies fetched: {len(policies)}")
    return policies

# YAML writing function
def append_to_yaml_file(data, account_id):
    file_name = f'combined-iam-{account_id}.yaml'
    with open(file_name, 'a') as file:
        yaml.dump(data, file)
    logging.info(f"Output written to {file_name}")

# Main function
def main():
    logging.info("Script started...")

    exclude_paths = ['/aws-reserved/', '/aws-service-role/', '/service-role/', '/cdk-hnb']
    exclude_role_prefixes = ['cdk-hnb659fds', 'StackSet', 'stackset', 'AWSControlTower']

    # Get the account ID
    account_id = get_account_id()
    if not account_id:
        logging.error("Failed to retrieve account ID.")
        return

    # ----- Role Processing -----
    # List all roles in the account
    roles = list_iam_roles(exclude_paths, exclude_role_prefixes)
    # List roles in CloudFormation stacks
    cf_stack_roles = list_cf_stack_roles()
    # Filter out CloudFormation provisioned roles
    filtered_roles = [role for role in roles if role['RoleName'] not in cf_stack_roles]
    
    roles_data = [{'RoleName': role['RoleName'], 'RoleId': role['RoleId']} for role in filtered_roles]

    # ----- Policy Processing -----
    # List all policies in the account
    policies = list_iam_managed_policies()
    # List CloudFormation stack managed policies
    cf_stack_policies = list_cf_stack_policies(account_id)
    # Filter out CloudFormation provisioned policies
    filtered_policies = [policy for policy in policies if policy['Arn'] not in cf_stack_policies]
    
    policies_data = [{'PolicyName': policy['PolicyName'], 'PolicyId': policy['PolicyId']} for policy in filtered_policies]

    # Combine both roles and policies into a single YAML output
    combined_data = {
        'Roles': roles_data,
        'Policies': policies_data
    }

    append_to_yaml_file(combined_data, account_id)

if __name__ == "__main__":
    main()
