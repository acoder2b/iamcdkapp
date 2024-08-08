import boto3
import csv
from datetime import datetime

def get_cf_stack_roles():
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    paginator = cf_client.get_paginator('describe_stacks')
    roles = []

    for page in paginator.paginate():
        for stack in page['Stacks']:
            stack_name = stack['StackName']
            resources = cf_client.describe_stack_resources(StackName=stack_name)['StackResources']
            for resource in resources:
                if resource['ResourceType'] == 'AWS::IAM::Role':
                    physical_id = resource.get('PhysicalResourceId', None)
                    if not physical_id:
                        print(f"Warning: Missing PhysicalResourceId for resource {resource}")
                    roles.append({
                        'StackName': stack_name,
                        'LogicalID': resource['LogicalResourceId'],
                        'PhysicalID': physical_id,
                        'Type': resource['ResourceType'],
                        'Status': resource['ResourceStatus']
                    })

    return roles

def write_roles_to_csv(roles, output_csv):
    with open(output_csv, mode='w', newline='') as csv_file:
        fieldnames = ['StackName', 'LogicalID', 'PhysicalID', 'Type', 'Status']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        writer.writeheader()
        for role in roles:
            writer.writerow(role)

def main():
    account_id = boto3.client('sts').get_caller_identity()['Account']
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    output_csv = f'cf_iam_roles_{account_id}_{current_time}.csv'

    # Get IAM roles from CloudFormation stacks
    roles = get_cf_stack_roles()
    
    # Write roles to CSV
    write_roles_to_csv(roles, output_csv)
    
    print(f"CSV file {output_csv} created successfully with {len(roles)} roles.")

if __name__ == "__main__":
    main()
