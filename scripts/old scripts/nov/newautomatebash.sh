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
python3 newCdkImportAutomationScript.py
if [ $? -ne 0 ]; then
    echo "Error: cdkImportAutomationScript.py failed."
    exit 1
fi
echo "cdkImportAutomationScript.py completed."

# Step 4: Run CDK synth to generate the templates in cdk.out
echo "Step 4: Running cdk synth..."
cd ..
cdk synth
if [ $? -ne 0 ]; then
    echo "Error: cdk synth failed."
    exit 1
fi
echo "cdk synth completed successfully."

# Step 5: Extract stack template files from cdk.out for the current account
echo "Step 5: Extracting stack template files from cdk.out for account $ACCOUNT_ID..."
STACK_TEMPLATE_FILES=$(find "$(pwd)/cdk.out" -name "IamRoleConfigStack-$ACCOUNT_ID-*.template.json")

if [ -z "$STACK_TEMPLATE_FILES" ]; then
    echo "Error: No stack template files found for account $ACCOUNT_ID."
    exit 1
fi

echo "Stack template files found for account $ACCOUNT_ID:"
echo "$STACK_TEMPLATE_FILES"

# Step 6: Switch back to iamConfigs directory
echo "Step 6: Switching back to iamConfigs directory..."
IAM_CONFIGS_DIR=$(pwd)/iamConfigs
cd "$IAM_CONFIGS_DIR"
echo "Now in iamConfigs directory: $IAM_CONFIGS_DIR"

# Step 7: Process each stack template file and run resource-map-RolenamePolicies.py
for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    echo "Processing stack template file: $TEMPLATE_FILE"
    
    # Check if the input file exists
    if [ ! -f "$TEMPLATE_FILE" ]; then
        echo "Error: Input file '$TEMPLATE_FILE' not found."
        exit 1
    fi
    
    # Run resource-map-RolenamePolicies.py for the current stack template
    echo "Running resource-map-RolenamePolicies.py for $TEMPLATE_FILE..."
    python3 resource-map-RolenamePolicies.py "$TEMPLATE_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: resource-map-RolenamePolicies.py failed for $TEMPLATE_FILE."
        exit 1
    fi
    echo "resource-map-RolenamePolicies.py completed for $TEMPLATE_FILE."
    
    # Derive the expected resource map file name based on the template file name
    RESOURCE_MAP_FILE=$(basename "$TEMPLATE_FILE" .template.json).json

    # Check if the resource map file is created
    if [ ! -f "$RESOURCE_MAP_FILE" ]; then
        echo "Error: Resource map file not created for template $TEMPLATE_FILE."
        exit 1
    fi
    echo "Resource map file created: $RESOURCE_MAP_FILE"
done

# Step 8: First stage - Process each stack template file to generate resource map files
for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    echo "Processing stack template file: $TEMPLATE_FILE"
    
    # Run resource-map-RolenamePolicies.py for the current stack template
    echo "Running resource-map-RolenamePolicies.py for $TEMPLATE_FILE..."
    python3 "$RESOURCE_MAP_SCRIPT_PATH" "$TEMPLATE_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: resource-map-RolenamePolicies.py failed for $TEMPLATE_FILE."
        exit 1
    fi
    echo "resource-map-RolenamePolicies.py completed for $TEMPLATE_FILE."
    
    # Derive the expected resource map file name based on the template file name
    RESOURCE_MAP_FILE=$(basename "$TEMPLATE_FILE" .template.json).json

    # Check if the resource map file is created
    if [ ! -f "$RESOURCE_MAP_FILE" ]; then
        echo "Error: Resource map file not created for template $TEMPLATE_FILE."
        exit 1
    fi
    echo "Resource map file created: $RESOURCE_MAP_FILE"
done

# Step 9: Second stage - Perform CDK import for each stack template file
for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    # Derive the expected resource map file name based on the template file name
    RESOURCE_MAP_FILE=$(basename "$TEMPLATE_FILE" .template.json).json

    # Ensure the resource map file exists before running the CDK import
    if [ ! -f "$RESOURCE_MAP_FILE" ]; then
        echo "Error: Resource map file not found: $RESOURCE_MAP_FILE"
        exit 1
    fi
    
    # Step 10: Switch back to main app directory and run cdk import
    echo "Step 10: Switching back to main app directory..."
    cd ..
    MAIN_APP_DIR=$(pwd)
    echo "Now in main app directory: $MAIN_APP_DIR"

    # Run cdk import for each resource map file
    STACK_NAME=$(basename "$TEMPLATE_FILE" .template.json)
    echo "Running cdk import for $STACK_NAME with $RESOURCE_MAP_FILE..."
    cdk import "$STACK_NAME" -m "$IAM_CONFIGS_DIR/$RESOURCE_MAP_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: cdk import failed for stack $STACK_NAME."
        exit 1
    fi
    echo "cdk import completed for stack $STACK_NAME with $RESOURCE_MAP_FILE."

    # Step 11: Check CloudFormation drift status
    echo "Step 11: Checking CloudFormation stack drift status for $STACK_NAME..."
    DRIFT_DETECTION_OUTPUT=$(aws cloudformation detect-stack-drift --stack-name "$STACK_NAME")
    if [ $? -ne 0 ]; then
        echo "Error: Drift detection failed for stack $STACK_NAME."
        exit 1
    fi
    echo "CloudFormation drift detection completed for $STACK_NAME."
    echo "$DRIFT_DETECTION_OUTPUT"

    # Extract StackDriftDetectionId using grep and sed
    STACK_DRIFT_DETECTION_ID=$(echo "$DRIFT_DETECTION_OUTPUT" | grep '"StackDriftDetectionId"' | sed -E 's/.*: "(.*)".*/\1/')

    echo "Drift detection ID for $STACK_NAME: $STACK_DRIFT_DETECTION_ID"

    # Step 12: Check drift detection status periodically
    echo "Step 12: Checking drift detection status for detection ID $STACK_DRIFT_DETECTION_ID..."

    CHECK_INTERVAL=10  # Time (in seconds) between status checks
    STATUS=""

    while true; do
        DRIFT_STATUS_OUTPUT=$(aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id "$STACK_DRIFT_DETECTION_ID")
        STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | grep '"DetectionStatus"' | sed -E 's/.*: "(.*)".*/\1/')
        
        echo "Current drift detection status for $STACK_NAME: $STATUS"
        
        # If drift detection is complete, exit the loop
        if [ "$STATUS" = "DETECTION_COMPLETE" ] || [ "$STATUS" = "DETECTION_FAILED" ]; then
            break
        fi
        
        # Wait for the next check
        sleep $CHECK_INTERVAL
    done

    # Print the final drift status
    FINAL_DRIFT_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | grep '"StackDriftStatus"' | sed -E 's/.*: "(.*)".*/\1/')
    echo "Final stack drift status for $STACK_NAME: $FINAL_DRIFT_STATUS"
    
    # Switch back to iamConfigs for the next iteration
    cd "$IAM_CONFIGS_DIR"
done

echo "Script execution completed successfully."
