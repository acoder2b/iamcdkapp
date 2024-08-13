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
            account_ids = [account_ids] #Convert single account_id to a list
        region = data.get('region', 'us-east-1')
        return account_ids, region, data

# Function to combine roles for shared accounts
def combine_roles(existing_data, new_data):
    if 'roles' in existing_data and 'roles' in new_data:
        existing_data['roles'].extend(new_data['roles'])
    return existing_data

# Create CDK App
app = App()

# Dictionary to hold combined configurations for shared accounts
combined_configs = defaultdict(lambda: {'roles': []})

# Iterate over each YAML file in the directory
for file_path in glob.glob(f"{config_directory}/*.yaml"):
    account_ids, region, data = load_account_info(file_path)
    
    for account_id in account_ids:
        env = Environment(account=account_id, region=region)
        
        # If the account is already in the combined configs, combine the roles
        if account_id in combined_configs:
            combined_configs[account_id] = combine_roles(combined_configs[account_id], data)
        else:
            combined_configs[account_id] = data


# Now create stacks for each account with combined configurations
for account_id, config_data in combined_configs.items():
    env = Environment(account=account_id, region=config_data.get('region', 'us-east-1'))
    stack_name = f"IamRoleConfigStack-{account_id}"
    
    print(f"Creating stack {stack_name} for account {account_id}")
    
    # Pass the account_id explicitly to the stack
    IamRoleConfigStack(app, stack_name, env=env, file_path=None, config_data=config_data, account_id=account_id)

    
app.synth()
