#!/bin/bash

# Step 1: Echo current working directory and record it
echo "Step 1: Checking current working directory..."
CURRENT_DIR=$(pwd)
echo "Current working directory is: $CURRENT_DIR"

# Ensure the script is run from iamConfigs directory
if [[ "$CURRENT_DIR" != *"iamConfigs"* ]]; then
    echo "Error: Script must be run from the iamConfigs directory!"
    exit 1
fi

# Step 2: Fetch AWS account ID and record it
echo "Step 2: Fetching AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
if [ $? -ne 0 ]; then
    echo "Error: Unable to retrieve AWS account ID."
    exit 1
fi
echo "AWS Account ID is: $ACCOUNT_ID"

# Step 3: Check if required scripts are available
echo "Step 3: Checking for required scripts..."
IMPORT_SCRIPT="newCdkImportAutomationScript.py"
RESOURCE_MAP_SCRIPT="resource-map-RolenamePolicies.py"

if [ ! -f "$IMPORT_SCRIPT" ] || [ ! -f "$RESOURCE_MAP_SCRIPT" ]; then
    echo "Error: Required scripts not found in the current directory."
    exit 1
fi
echo "Required scripts found."

# Run the cdkImportAutomationScript.py
echo "Running $IMPORT_SCRIPT..."
python3 "$IMPORT_SCRIPT"
if [ $? -ne 0 ]; then
    echo "Error: $IMPORT_SCRIPT failed."
    exit 1
fi
echo "$IMPORT_SCRIPT completed successfully."

# Step 4: Switch to main app directory and run CDK Synth
echo "Step 4: Switching to main app directory..."
cd ..
MAIN_APP_DIR=$(pwd)
echo "Now in main app directory: $MAIN_APP_DIR"

echo "Running CDK synth..."
cdk synth
if [ $? -ne 0 ]; then
    echo "Error: CDK synth failed."
    exit 1
fi
echo "CDK synth completed successfully."

# Collect all stack names from cdk.out for the current account
echo "Collecting stack names from cdk.out for account $ACCOUNT_ID..."
STACK_TEMPLATE_FILES=$(find "$MAIN_APP_DIR/cdk.out" -name "IamRoleConfigStack-$ACCOUNT_ID-*.template.json")
if [ -z "$STACK_TEMPLATE_FILES" ]; then
    echo "Error: No stack templates found for account $ACCOUNT_ID."
    exit 1
fi
echo "Stack templates found for account $ACCOUNT_ID:"
echo "$STACK_TEMPLATE_FILES"

# Step 5: Process each stack template and run resource-map script
echo "Step 5: Running resource-map script for each stack template..."
cd "$CURRENT_DIR"  # Ensure we are back in the iamConfigs directory
STACK_NAMES=()
RESOURCE_MAP_FILES=()

for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    ABS_TEMPLATE_FILE=$(realpath "$TEMPLATE_FILE")  # Get absolute path to ensure correct access
    STACK_NAME=$(basename "$ABS_TEMPLATE_FILE" .template.json)
    echo "Processing stack template: $STACK_NAME with template file $ABS_TEMPLATE_FILE"

    echo "Running resource-map script for $STACK_NAME..."
    python3 "$RESOURCE_MAP_SCRIPT" "$ABS_TEMPLATE_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: $RESOURCE_MAP_SCRIPT failed for $STACK_NAME."
        exit 1
    fi
    echo "resource-map script completed for $STACK_NAME."

    # Record the resource map file name with the associated stack name for matching
    RESOURCE_MAP_FILE="$STACK_NAME.json"
    RESOURCE_MAP_FILES+=("$STACK_NAME:$RESOURCE_MAP_FILE")
    STACK_NAMES+=("$STACK_NAME")
done

echo "Resource map files created and recorded with associated stack names:"
echo "${RESOURCE_MAP_FILES[@]}"

# Step 6: Run CDK import for each stack with the matching resource map file
echo "Step 6: Running CDK import for each stack and resource map file..."
cd "$MAIN_APP_DIR"

for ENTRY in "${RESOURCE_MAP_FILES[@]}"; do
    # Split each entry into the stack name and resource map file
    STACK_NAME="${ENTRY%%:*}"
    RESOURCE_MAP_FILE="$CURRENT_DIR/${ENTRY##*:}"

    # Ensure the resource map file exists before running the CDK import
    if [ ! -f "$RESOURCE_MAP_FILE" ]; then
        echo "Error: Resource map file not found: $RESOURCE_MAP_FILE"
        exit 1
    fi

    echo "Running CDK import for $STACK_NAME with $RESOURCE_MAP_FILE..."
    cdk import "$STACK_NAME" -m "$RESOURCE_MAP_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: CDK import failed for stack $STACK_NAME."
        exit 1
    fi
    echo "CDK import completed for $STACK_NAME with $RESOURCE_MAP_FILE."
done

# Step 9: Start drift detection for each imported stack and collect detection IDs
echo "Step 9: Starting CloudFormation drift detection for each stack..."

STACK_NAMES_ARRAY=()
DETECTION_IDS_ARRAY=()

for STACK_NAME in "${STACK_NAMES[@]}"; do
    echo "Initiating drift detection for stack: $STACK_NAME..."
    
    # Run drift detection and capture output
    DRIFT_DETECTION_OUTPUT=$(aws cloudformation detect-stack-drift --stack-name "$STACK_NAME" --output text 2>&1)
    echo "Drift detection command output for $STACK_NAME:"
    echo "$DRIFT_DETECTION_OUTPUT"
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to initiate drift detection for stack $STACK_NAME."
        exit 1
    fi

    # Extract the detection ID using awk
    STACK_DRIFT_DETECTION_ID=$(echo "$DRIFT_DETECTION_OUTPUT" | awk '{print $1}')
    if [ -z "$STACK_DRIFT_DETECTION_ID" ]; then
        echo "Error: Unable to extract StackDriftDetectionId for $STACK_NAME."
        exit 1
    fi
    
    echo "Drift detection ID for $STACK_NAME: $STACK_DRIFT_DETECTION_ID"
    STACK_NAMES_ARRAY+=("$STACK_NAME")
    DETECTION_IDS_ARRAY+=("$STACK_DRIFT_DETECTION_ID")
done

echo "All drift detection IDs collected. Moving to drift status monitoring."

# Step 10: Monitor drift detection status for each stack
echo "Step 10: Monitoring drift detection status for each stack..."

CHECK_INTERVAL=10  # Time (in seconds) between status checks

for i in "${!STACK_NAMES_ARRAY[@]}"; do
    STACK_NAME="${STACK_NAMES_ARRAY[$i]}"
    STACK_DRIFT_DETECTION_ID="${DETECTION_IDS_ARRAY[$i]}"
    echo "Checking drift status for stack $STACK_NAME with detection ID $STACK_DRIFT_DETECTION_ID..."

    while true; do
        # Run command to get the drift detection status
        DRIFT_STATUS_OUTPUT=$(aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id "$STACK_DRIFT_DETECTION_ID" --output json)

        # Check if the output is valid JSON
        if ! echo "$DRIFT_STATUS_OUTPUT" | jq empty > /dev/null 2>&1; then
            echo "Error: Invalid JSON output from AWS CLI"
            echo "Raw output:"
            echo "$DRIFT_STATUS_OUTPUT"
            break
        fi

        # Extract the detection status and stack drift status using jq
        DETECTION_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | jq -r '.DetectionStatus')
        STACK_DRIFT_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | jq -r '.StackDriftStatus')

        echo "Drift detection status for $STACK_NAME (detection ID: $STACK_DRIFT_DETECTION_ID):"
        echo "$DRIFT_STATUS_OUTPUT"

        # Check for completion and print the final drift status
        if [[ "$DETECTION_STATUS" == "DETECTION_COMPLETE" ]]; then
            echo "Final drift status for $STACK_NAME: $STACK_DRIFT_STATUS"
            break
        elif [[ "$DETECTION_STATUS" == "DETECTION_FAILED" ]]; then
            echo "Drift detection failed for stack $STACK_NAME."
            break
        else
            echo "Current drift detection status for $STACK_NAME: $DETECTION_STATUS. Waiting for next check..."
        fi

        # Wait before checking status again
        sleep $CHECK_INTERVAL
    done
done

echo "Drift detection completed for all stacks."
