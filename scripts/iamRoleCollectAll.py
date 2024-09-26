import boto3
import csv
import logging
from datetime import datetime
from botocore.exceptions import BotoCoreError, ClientError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def list_iam_roles(exclude_paths, exclude_role_prefixes):
    """
    List all IAM roles in the account, excluding those with specified paths and prefixes.
    """
    iam_client = boto3.client('iam')
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
                    'RoleArn': role['Arn'],
                    'UnderCFN': 'No',
                    'CFNStackName': ''
                })

        logging.info(f"Total roles found after exclusion: {len(roles)}")
        return roles

    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error listing IAM roles: {error}")
        return roles


def list_cf_stack_roles():
    """
    List IAM roles provisioned by CloudFormation stacks in all enabled regions.
    """
    session = boto3.Session()
    cf_roles = {}

    try:
        enabled_regions = session.get_available_regions('cloudformation')
    except (BotoCoreError, ClientError) as error:
        logging.error(f"Error retrieving enabled regions: {error}")
        return cf_roles

    logging.info("Listing IAM roles from CloudFormation stacks in all enabled regions...")
    for region in enabled_regions:
        try:
            cf_client = session.client('cloudformation', region_name=region)
            paginator = cf_client.get_paginator('describe_stacks')
            for page in paginator.paginate():
                for stack in page['Stacks']:
                    stack_name = stack['StackName']
                    resources = cf_client.describe_stack_resources(StackName=stack_name)['StackResources']
                    for resource in resources:
                        if resource['ResourceType'] == 'AWS::IAM::Role':
                            cf_roles[resource['PhysicalResourceId']] = stack_name
                            logging.info(f"Role '{resource['PhysicalResourceId']}' is provisioned by CloudFormation stack '{stack_name}' in region '{region}'.")

        except (BotoCoreError, ClientError) as error:
            if 'InvalidClientTokenId' in str(error):
                logging.warning(f"Region {region} is not enabled for this account. Skipping.")
            else:
                logging.error(f"Error listing CloudFormation stack roles in region {region}: {error}")

    logging.info(f"Total IAM roles found in CloudFormation stacks across all enabled regions: {len(cf_roles)}")
    return cf_roles

def get_account_id():
    sts_client = boto3.client('sts')
    return sts_client.get_caller_identity()['Account']

def write_roles_to_csv(roles, cf_roles, output_csv):
    with open(output_csv, mode='w', newline='') as csv_file:
        fieldnames = ['RoleName', 'RoleArn', 'UnderCFN', 'CFNStackName']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        writer.writeheader()
        for role in roles:
            if role['RoleName'] in cf_roles:
                role['UnderCFN'] = 'Yes'
                role['CFNStackName'] = cf_roles[role['RoleName']]
            writer.writerow(role)

def main():
    exclude_paths = [
        '/aws-reserved/',
        '/aws-service-role/',
        '/service-role/',
        '/cdk-hnb'
    ]
    exclude_role_prefixes = ['cdk-hnb659fds']

    account_id = get_account_id()
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    output_csv = f'iam_roles_{account_id}_{current_time}.csv'

    # List all roles in the account
    roles = list_iam_roles(exclude_paths, exclude_role_prefixes)

    # List roles in CloudFormation stacks
    cf_roles = list_cf_stack_roles()

    # Write all roles to CSV, marking those that are part of CloudFormation stacks
    write_roles_to_csv(roles, cf_roles, output_csv)
    
    print(f"CSV file {output_csv} created successfully with {len(roles)} roles.")

if __name__ == "__main__":
    main()

