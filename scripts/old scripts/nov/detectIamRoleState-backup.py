import boto3
import yaml
import sys
from collections import OrderedDict

def get_iam_role_state(role_name):
    iam_client = boto3.client('iam')
    try:
        role = iam_client.get_role(RoleName=role_name)
        return role['Role']
    except iam_client.exceptions.NoSuchEntityException:
        print(f"The role {role_name} does not exist.")
        sys.exit(1)

def create_yaml_file(role_state):
    role_name = role_state['RoleName']
    description = role_state.get('Description', '')
    session_duration = role_state.get('MaxSessionDuration', 3600)
    iam_path = role_state.get('Path', '/')
    trust_policy = role_state.get('AssumeRolePolicyDocument', {})
    tags = [{'key': tag['Key'], 'value': tag['Value']} for tag in role_state.get('Tags', [])]

    # Get attached managed policies
    iam_client = boto3.client('iam')
    attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
    managed_policies = [policy['PolicyArn'] for policy in attached_policies]

    # Get permission boundary
    permission_boundary = role_state.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn', '')

    # Create YAML structure using OrderedDict to maintain order
    yaml_content = [
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
            ('tags', tags)
        ])
    ]

    # Custom representer for OrderedDict
    def dict_representer(dumper, data):
        return dumper.represent_dict(data.items())

    yaml.add_representer(OrderedDict, dict_representer)

    # Custom representer for lists to ensure correct indentation
    def list_representer(dumper, data):
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)

    yaml.add_representer(list, list_representer)

    # Save YAML file
    yaml_file_name = f"{role_name}.yaml"
    with open(yaml_file_name, 'w') as yaml_file:
        yaml.dump(yaml_content, yaml_file, default_flow_style=False, sort_keys=False)
    print(f"YAML file {yaml_file_name} created successfully.")

def main():
    role_name = input("Which IAM role do you want to collect the details for? ")
    role_state = get_iam_role_state(role_name)
    create_yaml_file(role_state)

if __name__ == "__main__":
    main()
