import boto3
import csv
from datetime import datetime

def list_iam_roles(exclude_paths, exclude_role_prefix):
    iam_client = boto3.client('iam', region_name='us-east-1')
    paginator = iam_client.get_paginator('list_roles')
    roles = []

    for page in paginator.paginate():
        for role in page['Roles']:
            role_path = role['Path']
            role_name = role['RoleName']
            if not role['Arn'].startswith('arn:aws:iam::aws:role/') and \
               not any(role_path.startswith(path) for path in exclude_paths) and \
               not role_name.startswith(exclude_role_prefix):
                roles.append({
                    'RoleName': role['RoleName'],
                    'RoleArn': role['Arn']
                })
            else:
                print(f"Excluded role: {role_name} with path: {role_path}")

    return roles

def list_cf_stack_roles():
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('describe_stacks')
    roles = []

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
                    print(f"Found IAM Role in CFN Stack: {role_info}")

    return roles

def get_account_id():
    sts_client = boto3.client('sts', region_name='us-east-1')
    identity = sts_client.get_caller_identity()
    return identity['Account']

def write_roles_to_csv(roles, output_csv):
    with open(output_csv, mode='w', newline='') as csv_file:
        fieldnames = ['RoleName', 'RoleArn']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        writer.writeheader()
        for role in roles:
            writer.writerow(role)

def main():
    exclude_paths = [
        '/aws-reserved/',
        '/aws-service-role/',
        '/service-role/',
        '/cdk-hnb'
    ]
    exclude_role_prefix = 'cdk-hnb659fds'

    account_id = get_account_id()
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    output_csv = f'iam_roles_{account_id}_{current_time}.csv'

    # List all roles in the account
    roles = list_iam_roles(exclude_paths, exclude_role_prefix)

    # List roles in CloudFormation stacks
    cf_stack_roles = list_cf_stack_roles()

    # Create a set of Role Names provisioned by CloudFormation stacks
    cf_stack_role_names = {role['PhysicalID'] for role in cf_stack_roles}

    # Exclude roles that are part of CloudFormation stacks
    filtered_roles = [role for role in roles if role['RoleName'] not in cf_stack_role_names]

    # Write the filtered roles to CSV
    write_roles_to_csv(filtered_roles, output_csv)
    
    print(f"CSV file {output_csv} created successfully with {len(filtered_roles)} roles.")

if __name__ == "__main__":
    main()
