import boto3
import yaml
import csv
from collections import OrderedDict
from datetime import datetime
import sys
import os

def get_iam_role_state(role_name):
    iam_client = boto3.client('iam')
    try:
        role = iam_client.get_role(RoleName=role_name)
        return role['Role']
    except iam_client.exceptions.NoSuchEntityException:
        print(f"The role {role_name} does not exist.")
        return None

def get_inline_policies(role_name):
    iam_client = boto3.client('iam')
    inline_policies = {}
    try:
        policies = iam_client.list_role_policies(RoleName=role_name)['PolicyNames']
        for policy_name in policies:
            policy_document = iam_client.get_role_policy(RoleName=role_name, PolicyName=policy_name)['PolicyDocument']
            inline_policies[policy_name] = policy_document
    except Exception as e:
        print(f"Error fetching inline policies for role {role_name}: {e}")
    
    return inline_policies

def create_yaml_file(roles_data):
    yaml_content = []
    
    for role_data in roles_data:
        role_name = role_data['RoleName']
        description = role_data.get('Description')
        session_duration = role_data.get('MaxSessionDuration')
        iam_path = role_data.get('Path')
        trust_policy = role_data.get('AssumeRolePolicyDocument', {})
        tags = [{'key': tag['Key'], 'value': tag['Value']} for tag in role_data.get('Tags', [])] if 'Tags' in role_data else None

        # Get attached managed policies
        iam_client = boto3.client('iam')
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
        managed_policies = [policy['PolicyArn'] for policy in attached_policies] if attached_policies else None

        # Get inline policies
        inline_policies = get_inline_policies(role_name) if get_inline_policies(role_name) else None

        # Get permission boundary
        permission_boundary = role_data.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn') if role_data.get('PermissionsBoundary') else None

        # Create YAML structure using OrderedDict to maintain order
        role_dict = OrderedDict([('roleName', role_name)])

        if description:
            role_dict['description'] = description
        if session_duration:
            role_dict['sessionDuration'] = session_duration
        if iam_path:
            role_dict['iamPath'] = iam_path
        if trust_policy:
            trust_policy_statements = []
            for statement in trust_policy.get('Statement', []):
                statement_dict = OrderedDict([
                    ('Effect', statement['Effect']),
                    ('Principal', OrderedDict([
                        (key, value if isinstance(value, list) else [value])
                        for key, value in statement['Principal'].items()
                    ])),
                    ('Action', statement['Action'])
                ])
                # Only add Condition if it exists and is not empty
                if 'Condition' in statement and statement['Condition']:
                    statement_dict['Condition'] = statement['Condition']
                trust_policy_statements.append(statement_dict)

            role_dict['trustPolicy'] = OrderedDict([
                ('Version', trust_policy.get('Version', '2012-10-17')),
                ('Statement', trust_policy_statements)
            ])
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

    # Wrap the roles in a top-level dictionary with a key 'roles'
    final_yaml_content = yaml_content




    # Custom representer for OrderedDict
    def dict_representer(dumper, data):
        return dumper.represent_dict(data.items())

    yaml.add_representer(OrderedDict, dict_representer)

    # Custom representer for lists to ensure correct indentation
    def list_representer(dumper, data):
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)

    yaml.add_representer(list, list_representer)
    # Save YAML file
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    yaml_file_name = f"iam_roles_{current_time}.yaml"
    with open(yaml_file_name, 'w') as yaml_file:
        yaml.dump(yaml_content, yaml_file, default_flow_style=False, sort_keys=False)
    print(f"YAML file {yaml_file_name} created successfully.")



def main():
    # Check if the CSV file path is provided as a command-line argument
    if len(sys.argv) > 1:
        input_csv = sys.argv[1]
    else:
        print("CSV file path not provided")
        sys.exit(1)

    # Check if the file exists
    if not os.path.exists(input_csv):
        print(f"The file {input_csv} does not exist.")
        sys.exit(1)

    roles_data = []

    try:
        with open(input_csv, newline='') as csvfile:
            csvreader = csv.DictReader(csvfile)
            for row in csvreader:
                role_name = row['RoleName']
                role_arn = row['RoleArn']
                role_state = get_iam_role_state(role_name)
                if role_state:
                    roles_data.append(role_state)
    except FileNotFoundError:
        print(f"The file {input_csv} does not exist.")
        sys.exit(1)
    except KeyError:
        print("The CSV file should contain 'RoleName' and 'RoleArn' columns.")
        sys.exit(1)

    if roles_data:
        create_yaml_file(roles_data)
    else:
        print("No valid role data found to process.")

if __name__ == "__main__":
    main()
