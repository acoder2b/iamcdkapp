import boto3
import yaml
import csv
from collections import OrderedDict
from datetime import datetime
import sys

def get_iam_role_state(role_name):
    iam_client = boto3.client('iam')
    try:
        role = iam_client.get_role(RoleName=role_name)
        return role['Role']
    except iam_client.exceptions.NoSuchEntityException:
        print(f"The role {role_name} does not exist.")
        return None

def create_yaml_file(roles_data):
    yaml_content = []
    
    for role_data in roles_data:
        role_name = role_data['RoleName']
        description = role_data.get('Description', '')
        session_duration = role_data.get('MaxSessionDuration', 3600)
        iam_path = role_data.get('Path', '/')
        trust_policy = role_data.get('AssumeRolePolicyDocument', {})
        tags = [{'key': tag['Key'], 'value': tag['Value']} for tag in role_data.get('Tags', [])]

        # Get attached managed policies
        iam_client = boto3.client('iam')
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
        managed_policies = [policy['PolicyArn'] for policy in attached_policies]

        # Get permission boundary
        permission_boundary = role_data.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn', '')

        # Create YAML structure using OrderedDict to maintain order
        yaml_content.append(
            OrderedDict([
                ('roleName', role_name),
                ('description', description),
                ('sessionDuration', session_duration),
                ('iamPath', iam_path),
                ('trustPolicy', OrderedDict([
                    ('Version', trust_policy.get('Version', '2012-10-17')),
                    ('Statement', [
                        OrderedDict([
                            ('Effect', statement['Effect']),
                            ('Principal', OrderedDict([
                                (key, value if isinstance(value, list) else [value])
                                for key, value in statement['Principal'].items()
                            ])),
                            ('Action', statement['Action']),
                            ('Condition', statement.get('Condition', {}))
                        ]) for statement in trust_policy.get('Statement', [])
                    ])
                ])),
                ('externalIds', []),  # Add external IDs if applicable
                ('managedPolicies', managed_policies),
                ('permissionBoundary', permission_boundary),
                ('tags', tags),
                ('deletionPolicy', 'RETAIN')  # Add deletionPolicy flag
            ])
        )

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
    input_csv = input("Enter the CSV file path with role names and ARNs: ")
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
