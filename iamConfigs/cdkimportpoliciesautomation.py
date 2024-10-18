import boto3
import yaml
import logging
from botocore.exceptions import BotoCoreError, ClientError


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def list_cf_stack_policies(account_id):
    """
    List IAM managed policies provisioned by CloudFormation stacks.
    """
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('describe_stacks')
    cf_policy_arns = []

    logging.info("Listing IAM managed policies provisioned by CloudFormation stacks...")
    try:
        for page in paginator.paginate():
            for stack in page['Stacks']:
                stack_name = stack['StackName']
                resources = cf_client.describe_stack_resources(StackName=stack_name)['StackResources']
                for resource in resources:
                    if resource['ResourceType'] == 'AWS::IAM::ManagedPolicy':
                        physical_id = resource['PhysicalResourceId']
                        policy_arn = f'arn:aws:iam::{account_id}:policy/{physical_id}'
                        cf_policy_arns.append(policy_arn)
                        logging.info(f"Managed Policy '{policy_arn}' is provisioned by CloudFormation stack '{stack_name}'.")

        logging.info(f"Total IAM managed policies in CloudFormation stacks found: {len(cf_policy_arns)}")
        return cf_policy_arns

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing CloudFormation managed policies: {error}")
        return []


def list_customer_managed_policies():
    """
    List all customer-managed IAM policies, excluding those with /service-role/ path.
    """
    iam_client = boto3.client('iam', region_name='us-east-1')
    paginator = iam_client.get_paginator('list_policies')
    policies = []

    logging.info("Listing IAM customer-managed policies...")
    try:
        for page in paginator.paginate(Scope='Local'):
            for policy in page['Policies']:
                # Exclude policies with '/service-role/' path
                if '/service-role/' in policy.get('Path', ''):
                    logging.info(f"Skipping policy '{policy['PolicyName']}' with path '{policy['Path']}'")
                    continue

                policies.append({
                    'PolicyName': policy['PolicyName'],
                    'PolicyArn': policy['Arn'],
                    'PolicyId': policy['PolicyId'],
                    'Path': policy.get('Path')  # Include path in case it's useful later
                })
        logging.info(f"Total customer-managed policies found: {len(policies)}")
        return policies

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing IAM policies: {error}")
        return []


def get_policy_details(policy_arn):
    """
    Get details of a customer-managed IAM policy by its ARN.
    """
    iam_client = boto3.client('iam')
    try:
        policy = iam_client.get_policy(PolicyArn=policy_arn)['Policy']
        policy_version = iam_client.get_policy_version(
            PolicyArn=policy_arn,
            VersionId=policy['DefaultVersionId']
        )['PolicyVersion']['Document']
        
        return {
            'PolicyName': policy['PolicyName'],
            'Description': policy.get('Description'),
            'Path': policy.get('Path'),
            'PolicyDocument': policy_version
        }
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error fetching IAM policy details for {policy_arn}: {error}")
        return None


def filter_policies(policies, cf_policy_arns):
    """
    Filter out policies provisioned by CloudFormation.
    """
    filtered_policies = [policy for policy in policies if policy['PolicyArn'] not in cf_policy_arns]
    logging.info(f"Total customer-managed policies after filtering CloudFormation provisioned ones: {len(filtered_policies)}")
    return filtered_policies


def create_yaml_content(policies):
    """
    Create a YAML content structure for IAM managed policies, only including present details.
    """
    yaml_content = []

    logging.info("Creating YAML content for IAM policies...")
    for policy in policies:
        # Only include fields if they exist
        policy_dict = {
            'policyName': policy['PolicyName'],
            'deletionPolicy': 'RETAIN'  # Assuming we want to retain the policies by default
        }

        if policy.get('PolicyDocument'):
            policy_dict['policyDocument'] = policy['PolicyDocument']

        if policy.get('Description'):
            policy_dict['description'] = policy['Description']

        if policy.get('Path'):
            policy_dict['path'] = policy['Path']

        yaml_content.append(policy_dict)

    return yaml_content


def append_to_yaml_file(yaml_content, account_id):
    """
    Write the filtered policies to the YAML file.
    """
    yaml_file_name = f"iampolicy-{account_id}.yaml"

    yaml_structure = {
        'account_id': [account_id],
        'region': 'us-east-1',
        'stack_name': 'iampipeline-iampolicies-stack',
        'iam_policies': yaml_content
    }

    try:
        with open(yaml_file_name, 'w') as yaml_file:
            yaml.dump(yaml_structure, yaml_file, default_flow_style=False, sort_keys=False, indent=4)
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

    account_id = get_account_id()

    if not account_id:
        logging.error("Failed to retrieve account ID.")
        return

    # Step 1: List all customer-managed policies excluding those with /service-role/ path
    customer_managed_policies = list_customer_managed_policies()

    # Step 2: List IAM policies provisioned by CloudFormation stacks
    cf_stack_policy_arns = list_cf_stack_policies(account_id)

    # Step 3: Filter out policies provisioned by CloudFormation
    filtered_policies = filter_policies(customer_managed_policies, cf_stack_policy_arns)

    # Step 4: Get detailed information about the filtered policies
    detailed_policies = []
    for policy in filtered_policies:
        policy_details = get_policy_details(policy['PolicyArn'])
        if policy_details:
            detailed_policies.append(policy_details)

    # Step 5: Create YAML content for the filtered policies
    yaml_content = create_yaml_content(detailed_policies)

    # Step 6: Append the filtered policies to the YAML file
    append_to_yaml_file(yaml_content, account_id)

    logging.info("Script finished successfully.")


if __name__ == "__main__":
    main()
