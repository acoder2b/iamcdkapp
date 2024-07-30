import os
import logging
from dotenv import load_dotenv
from aws_cdk import App
# from iam_role_config_stack import IamRoleConfigStack
from iam_cdk_app.iam_cdk_app_stack import IamRoleConfigStack

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fetch environment variables
file_path = os.getenv('IAM_ROLE_CONFIG_FILE', 'iamConfigs/iamrole1.yaml')

# Create CDK App
app = App()
IamRoleConfigStack(app, "IamRoleConfigStack", file_path=file_path)
app.synth()
