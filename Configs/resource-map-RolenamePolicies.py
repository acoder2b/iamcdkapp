import json
import yaml
import argparse
import boto3
import os

def get_aws_account_id():
    """Fetch AWS account ID using local credentials via boto3."""
    client = boto3.client('sts')
    account_id = client.get_caller_identity()["Account"]
    return account_id

def extract_stack_name(resource_metadata):
    """
    Extract the stack name from the aws:cdk:path metadata field.
    The stack name is the first part of the value before the first '/'.
    """
    cdk_path = resource_metadata.get('aws:cdk:path')
    if cdk_path:
        # Split the aws:cdk:path to get the stack name before the first '/'
        return cdk_path.split('/')[0]
    return None

def generate_resource_map(file_name):
    # Check if the input file exists
    if not os.path.exists(file_name):
        print(f"Error: Input file '{file_name}' not found.")
        return

    with open(file_name, 'r') as f:
        # Parse the input YAML or JSON file
        data = yaml.safe_load(f)

    # Fetch AWS account ID using boto3
    account_id = get_aws_account_id()

    # Initialize the resource map
    resource_map = {}

    # Initialize stack_name variable
    stack_name = None

    # Iterate over the resources to find ManagedPolicyName, RoleName, and Metadata for stack_name
    for resource_name, resource_data in data.get('Resources', {}).items():
        # Extract stack_name from Metadata (aws:cdk:path) if not already found
        if not stack_name and 'Metadata' in resource_data:
            stack_name = extract_stack_name(resource_data['Metadata'])

        # Handle AWS::IAM::ManagedPolicy resources
        if resource_data.get('Type') == 'AWS::IAM::ManagedPolicy':
            managed_policy_name = resource_data.get('Properties', {}).get('ManagedPolicyName')
            if managed_policy_name:
                # Construct the ARN for ManagedPolicy
                policy_arn = f"arn:aws:iam::{account_id}:policy/{managed_policy_name}"

                # Add to the resource map using the logical resource name
                resource_map[resource_name] = {
                    "PolicyArn": policy_arn
                }

        # Handle AWS::IAM::Role resources
        elif resource_data.get('Type') == 'AWS::IAM::Role':
            role_name = resource_data.get('Properties', {}).get('RoleName')
            if role_name:
                # Construct the ARN for Role
                role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

                # Add to the resource map using the logical resource name
                resource_map[resource_name] = {
                    "RoleName": role_name
                }

    # If no stack_name was found, output an error
    if not stack_name:
        print(f"Error: 'aws:cdk:path' metadata not found in input file '{file_name}'.")
        return

    # Construct the output file name using the stack_name and AWS account ID
    output_file = f"{stack_name}.json"

    # Write the resource map to a JSON file
    with open(output_file, 'w') as outfile:
        json.dump(resource_map, outfile, indent=2)

    print(f"Resource map written to {output_file}")

if __name__ == "__main__":
    # Set up argument parser to take the input file name
    parser = argparse.ArgumentParser(description="Generate a resource map from a CloudFormation template")
    parser.add_argument("input_file", help="Path to the input YAML or JSON file")
    
    # Parse the command-line arguments
    args = parser.parse_args()

    # Generate resource map using the provided input file
    generate_resource_map(args.input_file)
