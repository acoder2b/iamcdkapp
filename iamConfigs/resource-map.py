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

    # Construct the output file name using the account ID
    output_file = f"resource-map-{account_id}.json"

    # Initialize the resource map
    resource_map = {}

    # Iterate over the resources to find ManagedPolicyName and RoleName
    for resource_name, resource_data in data.get('Resources', {}).items():
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
                    "RoleArn": role_arn
                }

    # Write the resource map to a JSON file
    with open(output_file, 'w') as outfile:
        json.dump(resource_map, outfile, indent=2)

    print(f"Resource map written to {output_file}")

if __name__ == "__main__":
    # Set up argument parser to take the input file name
    parser = argparse.ArgumentParser(description="Generate a resource map from a YAML or JSON file")
    parser.add_argument("input_file", help="Path to the input YAML or JSON file")
    
    # Parse the command-line arguments
    args = parser.parse_args()

    # Generate resource map using the provided input file
    generate_resource_map(args.input_file)
