import os
import logging
from dotenv import load_dotenv
from aws_cdk import App, Environment
# from iam_role_config_stack import IamRoleConfigStack
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack
import glob
import yaml

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory containing YAML files
config_directory = os.getenv('IAM_ROLE_CONFIG_DIRECTORY', 'iamConfigs')

# # Fetch environment variables
# file_path = os.getenv('IAM_ROLE_CONFIG_FILE', 'iamConfigs/iamrole1.yaml')

# app = App(analytics_reporting=False)  

# Function to load account ID and region from YAML file
def load_account_info(file_path):
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
        account_id = data.get('account_id')
        region = data.get('region', 'us-east-1')
        return account_id, region



# Create CDK App
app = App()
 # Disable CDK Metadata
app.node.set_context("cdk.metadata", False)

# IamRoleConfigStack(app, "IamRoleConfigStack", file_path=file_path)

# # Iterate over each YAML file in the directory
for file_path in glob.glob(f"{config_directory}/*.yaml"):
    account_id, region = load_account_info(file_path)
    env = Environment(account=account_id, region=region)
    stack_name = f"IamRoleConfigStack-{account_id}"
    print("Creating stack for : " + file_path)
    IamRoleConfigStack(app, stack_name, env=env, file_path=file_path)


    
app.synth()
