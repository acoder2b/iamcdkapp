#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.
set -o pipefail  # Return value of a pipeline is the value of the last (rightmost) command to exit with a non-zero status.

# Function to log messages with timestamps
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required commands
for cmd in aws jq cdk python3; do
    if ! command_exists "$cmd"; then
        log "Error: $cmd is not installed or not in PATH"
        exit 1
    fi
done

# Configuration
CURRENT_DIR=$(pwd)
IMPORT_SCRIPT="newCdkImportAutomationScript.py"
RESOURCE_MAP_SCRIPT="resource-map-RolenamePolicies.py"
CHECK_INTERVAL=10  # Time (in seconds) between status checks
MAX_RETRIES=30     # Maximum number of retries for drift detection status

# Step 1: Check current working directory
log "Step 1: Checking current working directory..."
if [[ "$CURRENT_DIR" != *"iamConfigs"* ]]; then
    log "Error: Script must be run from the iamConfigs directory!"
    exit 1
fi
log "Current working directory is: $CURRENT_DIR"

# Step 2: Fetch AWS account ID
log "Step 2: Fetching AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
if [ $? -ne 0 ]; then
    log "Error: Unable to retrieve AWS account ID."
    exit 1
fi
log "AWS Account ID is: $ACCOUNT_ID"

# Step 3: Check for required scripts
log "Step 3: Checking for required scripts..."
for script in "$IMPORT_SCRIPT" "$RESOURCE_MAP_SCRIPT"; do
    if [ ! -f "$script" ]; then
        log "Error: Required script $script not found in the current directory."
        exit 1
    fi
done
log "Required scripts found."

# Run the cdkImportAutomationScript.py
log "Running $IMPORT_SCRIPT..."
python3 "$IMPORT_SCRIPT"
if [ $? -ne 0 ]; then
    log "Error: $IMPORT_SCRIPT failed."
    exit 1
fi
log "$IMPORT_SCRIPT completed successfully."

# Step 4: Switch to main app directory and run CDK Synth
log "Step 4: Switching to main app directory..."
cd ..
MAIN_APP_DIR=$(pwd)
log "Now in main app directory: $MAIN_APP_DIR"

log "Running CDK synth..."
cdk synth
if [ $? -ne 0 ]; then
    log "Error: CDK synth failed."
    exit 1
fi
log "CDK synth completed successfully."

# Collect all stack names from cdk.out for the current account
log "Collecting stack names from cdk.out for account $ACCOUNT_ID..."
STACK_TEMPLATE_FILES=$(find "$MAIN_APP_DIR/cdk.out" -name "IamRoleConfigStack-$ACCOUNT_ID-*.template.json")
if [ -z "$STACK_TEMPLATE_FILES" ]; then
    log "Error: No stack templates found for account $ACCOUNT_ID."
    exit 1
fi
log "Stack templates found for account $ACCOUNT_ID:"
echo "$STACK_TEMPLATE_FILES"

# Step 5: Process each stack template and run resource-map script
log "Step 5: Running resource-map script for each stack template..."
cd "$CURRENT_DIR"  # Ensure we are back in the iamConfigs directory
STACK_NAMES=()
RESOURCE_MAP_FILES=()

for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    ABS_TEMPLATE_FILE=$(realpath "$TEMPLATE_FILE")
    STACK_NAME=$(basename "$ABS_TEMPLATE_FILE" .template.json)
    log "Processing stack template: $STACK_NAME with template file $ABS_TEMPLATE_FILE"

    log "Running resource-map script for $STACK_NAME..."
    python3 "$RESOURCE_MAP_SCRIPT" "$ABS_TEMPLATE_FILE"
    if [ $? -ne 0 ]; then
        log "Error: $RESOURCE_MAP_SCRIPT failed for $STACK_NAME."
        exit 1
    fi
    log "resource-map script completed for $STACK_NAME."

    RESOURCE_MAP_FILE="$STACK_NAME.json"
    RESOURCE_MAP_FILES+=("$STACK_NAME:$RESOURCE_MAP_FILE")
    STACK_NAMES+=("$STACK_NAME")
done

log "Resource map files created and recorded with associated stack names:"
printf '%s\n' "${RESOURCE_MAP_FILES[@]}"

# Step 6: Run CDK import for each stack with the matching resource map file
log "Step 6: Running CDK import for each stack and resource map file..."
cd "$MAIN_APP_DIR"

for ENTRY in "${RESOURCE_MAP_FILES[@]}"; do
    STACK_NAME="${ENTRY%%:*}"
    RESOURCE_MAP_FILE="$CURRENT_DIR/${ENTRY##*:}"

    if [ ! -f "$RESOURCE_MAP_FILE" ]; then
        log "Error: Resource map file not found: $RESOURCE_MAP_FILE"
        exit 1
    fi

    log "Running CDK import for $STACK_NAME with $RESOURCE_MAP_FILE..."
    cdk import "$STACK_NAME" -m "$RESOURCE_MAP_FILE"
    if [ $? -ne 0 ]; then
        log "Error: CDK import failed for stack $STACK_NAME."
        exit 1
    fi
    log "CDK import completed for $STACK_NAME with $RESOURCE_MAP_FILE."
done

# Step 9: Start drift detection for each imported stack and collect detection IDs
log "Step 9: Starting CloudFormation drift detection for each stack..."

STACK_NAMES_ARRAY=()
DETECTION_IDS_ARRAY=()

for STACK_NAME in "${STACK_NAMES[@]}"; do
    log "Initiating drift detection for stack: $STACK_NAME..."
    
    DRIFT_DETECTION_OUTPUT=$(aws cloudformation detect-stack-drift --stack-name "$STACK_NAME" --output json)
    if [ $? -ne 0 ]; then
        log "Error: Failed to initiate drift detection for stack $STACK_NAME."
        log "AWS CLI output: $DRIFT_DETECTION_OUTPUT"
        exit 1
    fi

    STACK_DRIFT_DETECTION_ID=$(echo "$DRIFT_DETECTION_OUTPUT" | jq -r '.StackDriftDetectionId')
    if [ -z "$STACK_DRIFT_DETECTION_ID" ]; then
        log "Error: Unable to extract StackDriftDetectionId for $STACK_NAME."
        log "AWS CLI output: $DRIFT_DETECTION_OUTPUT"
        exit 1
    fi
    
    log "Drift detection ID for $STACK_NAME: $STACK_DRIFT_DETECTION_ID"
    STACK_NAMES_ARRAY+=("$STACK_NAME")
    DETECTION_IDS_ARRAY+=("$STACK_DRIFT_DETECTION_ID")
done

log "All drift detection IDs collected. Moving to drift status monitoring."

# Step 10: Monitor drift detection status for each stack
log "Step 10: Monitoring drift detection status for each stack..."

for i in "${!STACK_NAMES_ARRAY[@]}"; do
    STACK_NAME="${STACK_NAMES_ARRAY[$i]}"
    STACK_DRIFT_DETECTION_ID="${DETECTION_IDS_ARRAY[$i]}"
    log "Checking drift status for stack $STACK_NAME with detection ID $STACK_DRIFT_DETECTION_ID..."

    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        DRIFT_STATUS_OUTPUT=$(aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id "$STACK_DRIFT_DETECTION_ID" --output json)
        
        if ! echo "$DRIFT_STATUS_OUTPUT" | jq empty > /dev/null 2>&1; then
            log "Error: Invalid JSON output from AWS CLI"
            log "Raw output: $DRIFT_STATUS_OUTPUT"
            break
        fi

        DETECTION_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | jq -r '.DetectionStatus')
        STACK_DRIFT_STATUS=$(echo "$DRIFT_STATUS_OUTPUT" | jq -r '.StackDriftStatus')

        log "Drift detection status for $STACK_NAME (detection ID: $STACK_DRIFT_DETECTION_ID):"
        echo "$DRIFT_STATUS_OUTPUT" | jq '.'

        if [[ "$DETECTION_STATUS" == "DETECTION_COMPLETE" ]]; then
            log "Final drift status for $STACK_NAME: $STACK_DRIFT_STATUS"
            break
        elif [[ "$DETECTION_STATUS" == "DETECTION_FAILED" ]]; then
            log "Drift detection failed for stack $STACK_NAME."
            break
        else
            log "Current drift detection status for $STACK_NAME: $DETECTION_STATUS. Waiting for next check..."
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        sleep $CHECK_INTERVAL
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        log "Warning: Maximum retries reached for stack $STACK_NAME. Final status: $DETECTION_STATUS"
    fi
done

log "Drift detection completed for all stacks."
