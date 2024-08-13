import os
import logging
import aws_cdk as cdk
from dotenv import load_dotenv
from aws_cdk import App, Environment
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack
import glob
import yaml
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory containing YAML files
config_directory = os.getenv('IAM_ROLE_CONFIG_DIRECTORY', 'iamConfigs')

# Function to load account ID and region from YAML file
def load_account_info(file_path):
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
        account_ids = data.get('account_id')
        if isinstance(account_ids, str):
            account_ids = [account_ids]  # Convert single account_id to a list
        roles = data.get('roles', [])
        return account_ids, roles

# # Function to filter and combine roles for shared accounts
# def combine_roles_for_account(existing_roles, new_roles):
#     # Combine only unique roles
#     role_names = {role['roleName'] for role in existing_roles}
#     for role in new_roles:
#         if role['roleName'] not in role_names:
#             existing_roles.append(role)
#             role_names.add(role['roleName'])
#     return existing_roles

# Create CDK App
app = App()

# Dictionary to hold combined configurations for shared accounts
combined_configs = dict()

# Create combined_configs with a mapping of account_id to roles
for file_path in glob.glob(f"{config_directory}/*.yaml"):
    account_ids, roles = load_account_info(file_path)
    for account_id in account_ids:
        if account_id not in combined_configs:
            combined_configs[account_id] = []
        combined_configs[account_id].extend(roles)


# # Iterate over each YAML file in the directory
# for file_path in glob.glob(f"{config_directory}/*.yaml"):
#     account_ids, region, roles = load_account_info(file_path)
    
#     for account_id in account_ids:
#         env = Environment(account=account_id, region=region)
        
#         if account_id in combined_configs:
#             combined_configs[account_id]['roles'] = combine_roles_for_account(combined_configs[account_id]['roles'], roles)
#             #print(f"combine_roles {account_id} role_count={len(roles)} file_path={file_path} total_role_count={len(combined_configs[account_id]['roles'])}")
#         else:
#             combined_configs[account_id]['roles'] = roles
#             combined_configs[account_id]['region'] = region
#             #print(f"add_new_roles {account_id} role_count={len(roles)} file_path={file_path} total_role_count={len(combined_configs[account_id]['roles'])}")
#         #print(f"role_count for 596905249077 = {len(combined_configs['596905249077']['roles'])}")


# Now create stacks for each account with combined configurations
for account_id, roles in combined_configs.items():
    env = Environment(account=account_id, region='us-east-1')
    stack_name = f"IamRoleConfigStack-{account_id}"

    #print(f"config_data {account_id} role_count={len(config_data['roles'])}")
    
    print(f"Creating stack {stack_name} for account {account_id}")
    
    # Pass the account_id explicitly to the stack
    IamRoleConfigStack(app, stack_name, env=env, file_path=None, roles=roles, account_id=account_id)

app.synth()
