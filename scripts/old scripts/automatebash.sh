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

# Get the absolute path of the script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIGS_DIR="$PROJECT_ROOT/Configs"

# Check for required commands
for cmd in aws jq cdk python3; do
    if ! command_exists "$cmd"; then
        log "Error: $cmd is not installed or not in PATH"
        exit 1
    fi
done

# Check for required commands
for cmd in aws jq cdk python3; do
    if ! command_exists "$cmd"; then
        log "Error: $cmd is not installed or not in PATH"
        exit 1
    fi
done

# Configuration
CURRENT_DIR=$(pwd)
IMPORT_SCRIPT="cdkImportAutomationScript.py"
RESOURCE_MAP_SCRIPT="resource-map-RolenamePolicies.py"
CHECK_INTERVAL=10  # Time (in seconds) between status checks
MAX_RETRIES=5    # Maximum number of retries for drift detection status

# Step 1: Check if required directories exist
log "Step 1: Checking required directories..."
if [ ! -d "$CONFIGS_DIR" ]; then
    log "Error: Configs directory not found at $CONFIGS_DIR"
    exit 1
fi
log "Configs directory found at: $CONFIGS_DIR"

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
if [ ! -f "$IMPORT_SCRIPT" ]; then
    log "Error: Import script not found at $IMPORT_SCRIPT"
    exit 1
fi
if [ ! -f "$RESOURCE_MAP_SCRIPT" ]; then
    log "Error: Resource map script not found at $RESOURCE_MAP_SCRIPT"
    exit 1
fi
log "Required scripts found."

# Step 4: Run the cdkImportAutomationScript.py
log "Running $IMPORT_SCRIPT..."
cd "$CONFIGS_DIR"
python3 "$IMPORT_SCRIPT"
if [ $? -ne 0 ]; then
    log "Error: $IMPORT_SCRIPT failed."
    exit 1
fi
log "$IMPORT_SCRIPT completed successfully."

# Step 5: Switch to main app directory and run CDK Synth
log "Step 4: Switching to main app directory..."
cd "$PROJECT_ROOT"
log "Now in main app directory: $MAIN_APP_DIR"

log "Running CDK synth..."
cdk synth
if [ $? -ne 0 ]; then
    log "Error: CDK synth failed."
    exit 1
fi
log "CDK synth completed successfully."

# Step 6: Collect all stack names from cdk.out for the current account
log "Collecting stack names from cdk.out for account $ACCOUNT_ID..."
STACK_TEMPLATE_FILES=$(find "$PROJECT_ROOT/cdk.out" -name "IamRoleConfigStack-$ACCOUNT_ID-iam-role-policies-*.template.json")
if [ -z "$STACK_TEMPLATE_FILES" ]; then
    log "Error: No stack templates found for account $ACCOUNT_ID."
    exit 1
fi
log "Stack templates found for account $ACCOUNT_ID:"
echo "$STACK_TEMPLATE_FILES"

# Step 7: Process each stack template and run resource-map script
log "Step 7: Running resource-map script for each stack template..."
# Create a temporary working directory for resource map outputs
TEMP_OUTPUT_DIR="$PROJECT_ROOT/temp_resource_maps"
mkdir -p "$TEMP_OUTPUT_DIR"

STACK_NAMES=()
RESOURCE_MAP_FILES=()

for TEMPLATE_FILE in $STACK_TEMPLATE_FILES; do
    ABS_TEMPLATE_FILE=$(realpath "$TEMPLATE_FILE")
    STACK_NAME=$(basename "$ABS_TEMPLATE_FILE" .template.json)
    log "Processing stack template: $STACK_NAME with template file $ABS_TEMPLATE_FILE"

    log "Running resource-map script for $STACK_NAME..."
    cd "$SCRIPT_DIR"  # Change to scripts directory to run resource-map script
    python3 "$RESOURCE_MAP_SCRIPT" "$ABS_TEMPLATE_FILE"
    if [ $? -ne 0 ]; then
        log "Error: Resource map script failed for $STACK_NAME."
        exit 1
    fi
    log "Resource map script completed for $STACK_NAME."

    # Move the generated resource map file to temp directory
    RESOURCE_MAP_FILE="$TEMP_OUTPUT_DIR/$STACK_NAME.json"
    mv "$STACK_NAME.json" "$RESOURCE_MAP_FILE"
    RESOURCE_MAP_FILES+=("$STACK_NAME:$RESOURCE_MAP_FILE")
    STACK_NAMES+=("$STACK_NAME")
done

log "Resource map files created and recorded with associated stack names:"
printf '%s\n' "${RESOURCE_MAP_FILES[@]}"

# Step 8: Run CDK import for each stack with the matching resource map file
log "Step 8: Running CDK import for each stack and resource map file..."
cd "$PROJECT_ROOT"

for ENTRY in "${RESOURCE_MAP_FILES[@]}"; do
    STACK_NAME="${ENTRY%%:*}"
    RESOURCE_MAP_FILE="${ENTRY##*:}"

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

# [Rest of the drift detection code remains the same, just ensure proper directory references]

# Cleanup temporary directory at the end
log "Cleaning up temporary files..."
rm -rf "$TEMP_OUTPUT_DIR"

log "Script execution completed successfully."

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
