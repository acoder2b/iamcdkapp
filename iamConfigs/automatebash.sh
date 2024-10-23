#!/bin/bash

# Record the current working directory
echo "Step 1: Checking current working directory..."
CURRENT_DIR=$(pwd)
echo "Current working directory is: $CURRENT_DIR"

# Ensure the script is run from iamConfigs directory
if [[ "$CURRENT_DIR" != *"iamConfigs"* ]]; then
    echo "Error: Script must be run from the iamConfigs directory!"
    exit 1
fi

# Step 2: Get AWS account ID
echo "Step 2: Fetching AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
if [ $? -ne 0 ]; then
    echo "Error: Unable to retrieve AWS account ID."
    exit 1
fi
echo "AWS Account ID is: $ACCOUNT_ID"

# Step 3: Run the cdkImportAutomationScript.py
echo "Step 3: Running cdkImportAutomationScript.py..."
python3 cdkImportAutomationScript.py
if [ $? -ne 0 ]; then
    echo "Error: cdkImportAutomationScript.py failed."
    exit 1
fi
echo "cdkImportAutomationScript.py completed."

# Step 4: Switch to main app directory
echo "Step 4: Changing to main app directory..."
cd ..
MAIN_APP_DIR=$(pwd)
echo "Now in main app directory: $MAIN_APP_DIR"

# Step 5: Run cdk synth and capture stack names
echo "Step 5: Running cdk synth..."
CDK_OUTPUT=$(cdk synth)
echo "cdk synth completed. Output:"
echo "$CDK_OUTPUT"

# Use awk to capture stack names from the output
STACK_NAMES=$(echo "$CDK_OUTPUT" | awk '/iam-role-policies-pipeline-stack for account/ {print "SecurityConfigStack-" $6 "-iam-role-policies-pipeline-stack"}')
echo "Stack names captured: $STACK_NAMES"

# Step 6: Switch back to iamConfigs
echo "Step 6: Switching back to iamConfigs directory..."
cd iamConfigs
IAM_CONFIGS_DIR=$(pwd)
echo "Now in iamConfigs directory: $IAM_CONFIGS_DIR"

# Step 7: Run resource-map-RolenamePolicies.py
echo "Step 7: Running resource-map-RolenamePolicies.py..."
cdk_out_file="../cdk.out/SecurityConfigStack-$ACCOUNT_ID-iam-role-policies-pipeline-stack.template.json"

# Check if the input file exists
if [ ! -f "$cdk_out_file" ]; then
    echo "Error: Input file '$cdk_out_file' not found."
    exit 1
fi

python3 resource-map-RolenamePolicies.py "$cdk_out_file"
if [ $? -ne 0 ]; then
    echo "Error: resource-map-RolenamePolicies.py failed."
    exit 1
fi
echo "resource-map-RolenamePolicies.py completed."

# Check if the resource map file is created
RESOURCE_MAP_FILE="resource-map-name-$ACCOUNT_ID.json"
if [ ! -f "$IAM_CONFIGS_DIR/$RESOURCE_MAP_FILE" ]; then
    echo "Error: Resource map file not created: $RESOURCE_MAP_FILE"
    exit 1
fi
echo "Resource map file created: $RESOURCE_MAP_FILE"

# Step 8: Switch back to main app directory and run cdk import
echo "Step 8: Switching back to main app directory..."
cd ..
MAIN_APP_DIR=$(pwd)
echo "Now in main app directory: $MAIN_APP_DIR"

# Run cdk import
STACK_NAME="SecurityConfigStack-$ACCOUNT_ID-iam-role-policies-pipeline-stack"
cdk import "$STACK_NAME" -m "$IAM_CONFIGS_DIR/$RESOURCE_MAP_FILE"
if [ $? -ne 0 ]; then
    echo "Error: cdk import failed."
    exit 1
fi
echo "cdk import completed."

# Step 9: Check CloudFormation drift status
echo "Step 9: Checking CloudFormation stack drift status..."
DRIFT_DETECTION_OUTPUT=$(aws cloudformation detect-stack-drift --stack-name "$STACK_NAME")
if [ $? -ne 0 ]; then
    echo "Error: Drift detection failed."
    exit 1
fi
echo "CloudFormation drift detection completed."
echo "$DRIFT_DETECTION_OUTPUT"

# Extract StackDriftDetectionId using grep and sed instead of jq
STACK_DRIFT_DETECTION_ID=$(echo "$DRIFT_DETECTION_OUTPUT" | grep '"StackDriftDetectionId"' | sed -E 's/.*: "(.*)".*/\1/')

echo "Drift detection ID: $STACK_DRIFT_DETECTION_ID"

# Step 10: Check drift detection status periodically
echo "Step 10: Checking drift detection status for detection ID $STACK_DRIFT_DETECTION_ID..."

CHECK_INTERVAL=10  # Time (in seconds) between status checks
STATUS=""

while true; do
    DRIFT_STATUS_OUTPUT=$(aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id "$STACK_DRIFT_DETECTION_ID")
    STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | grep '"DetectionStatus"' | sed -E 's/.*: "(.*)".*/\1/')
    
    echo "Current drift detection status: $STATUS"
    
    # If drift detection is complete, exit the loop
    if [ "$STATUS" = "DETECTION_COMPLETE" ] || [ "$STATUS" = "DETECTION_FAILED" ]; then
        break
    fi
    
    # Wait for the next check
    sleep $CHECK_INTERVAL
done

# Print the final drift status
FINAL_DRIFT_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | grep '"StackDriftStatus"' | sed -E 's/.*: "(.*)".*/\1/')
echo "Final stack drift status: $FINAL_DRIFT_STATUS"

echo "Script execution completed successfully."
