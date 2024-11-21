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

def get_account_id():
    sts_client = boto3.client('sts', region_name='us-east-1')
    identity = sts_client.get_caller_identity()
    return identity['Account']

def list_cf_stack_roles():
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('describe_stacks')
    stack_roles = set()

    for page in paginator.paginate():
        for stack in page['Stacks']:
            if 'RoleARN' in stack:
                stack_roles.add(stack['RoleARN'])
            
            # Check stack resources for roles
            resources = cf_client.describe_stack_resources(StackName=stack['StackName'])['StackResources']
            for resource in resources:
                if resource['ResourceType'] == 'AWS::IAM::Role':
                    stack_roles.add(resource.get('PhysicalResourceId', resource['LogicalResourceId']))

    return stack_roles

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

    # List all roles
    roles = list_iam_roles(exclude_paths, exclude_role_prefix)
    
    # List roles in CloudFormation stacks
    cf_stack_roles = list_cf_stack_roles()

    # Exclude roles that are part of CloudFormation stacks
    filtered_roles = [role for role in roles if role['RoleArn'] not in cf_stack_roles]

    # Validate roles against each CloudFormation template
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    stacks = cf_client.describe_stacks()['Stacks']

    final_roles = []
    for role in filtered_roles:
        role_used_in_stack = False
        for stack in stacks:
            template = cf_client.get_template(StackName=stack['StackName'])['TemplateBody']
            if role['RoleName'] in str(template):
                role_used_in_stack = True
                print(f"Role {role['RoleName']} is used in CloudFormation stack {stack['StackName']}")
                break
        if not role_used_in_stack:
            final_roles.append(role)

    write_roles_to_csv(final_roles, output_csv)
    print(f"CSV file {output_csv} created successfully with {len(final_roles)} roles.")

if __name__ == "__main__":
    main()
