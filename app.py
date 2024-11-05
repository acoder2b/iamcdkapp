# Copyright © Amazon.com and Affiliates: This deliverable is considered 
# Developed Content as defined in the AWS Service Terms and the SOW 
# between the parties dated August 13, 2024.

import os
import logging
import aws_cdk as cdk
from dotenv import load_dotenv
from aws_cdk import App, Environment
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack
import glob
import yaml
from collections import defaultdict
import hashlib

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory containing YAML files
config_directory = os.getenv('IAM_ROLE_CONFIG_DIRECTORY', 'iamConfigs')
# deployment_account_id = os.getenv('ACCOUNT_ID') # AWS Account ID that we are deploying the IAM roles to

# Function to load account ID and region from YAML file
def load_account_info(file_path):
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
        account_ids = data.get('account_id')
        stack_name = data.get('stack_name', 'default')
        if isinstance(account_ids, str):
            account_ids = [account_ids]  # Convert single account_id to a list
        roles = data.get('roles', [])
        iam_policies = data.get('iam_policies', [])
        return account_ids, roles, stack_name, iam_policies


# Create CDK App
app = App()

# Dictionary to hold combined configurations for shared accounts
combined_configs = dict()

# Create combined_configs with a mapping of account_id to roles
for file_path in glob.glob(f"{config_directory}/*.yaml"):
    account_ids, roles,  stack_name, iam_policies = load_account_info(file_path)
    for account_id in account_ids:
        if account_id not in combined_configs:
            combined_configs[account_id] = dict()
        if stack_name not in combined_configs[account_id]:
            combined_configs[account_id][stack_name] = dict()
            combined_configs[account_id][stack_name]["roles"] = []
            combined_configs[account_id][stack_name]["iam_policies"] = []
        combined_configs[account_id][stack_name]["roles"].extend(roles)
        combined_configs[account_id][stack_name]["iam_policies"].extend(iam_policies)



# Now create stacks for each account with combined configurations
for account_id, stacks in combined_configs.items():
    # if account_id != deployment_account_id: 
    #     continue
    env = Environment(account=account_id, region='us-east-1')
    # stack_name = f"IamRoleConfigStack-{account_id}"

    #print(f"config_data {account_id} role_count={len(config_data['roles'])}")
    for stack_name, resources  in stacks.items():
        cdk_stack_name = f"IamRoleConfigStack-{account_id}-{stack_name}"
        print(f"Creating stack {stack_name} for account {account_id}")
    
    # Pass the account_id explicitly to the stack
        IamRoleConfigStack(app, cdk_stack_name, env=env, file_path=None, resources=resources, account_id=account_id)

app.synth()
