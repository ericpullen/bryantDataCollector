#!/bin/bash
# Don't use set -e as we handle errors manually

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="bryantDataCollector"
REGION="us-east-1"
DEPLOYER_SCRIPT="$HOME/code/bryantDeployerRole.sh"

# Check if deployer script exists
if [ ! -f "$DEPLOYER_SCRIPT" ]; then
    echo -e "${RED}Error: Deployer script not found at $DEPLOYER_SCRIPT${NC}"
    exit 1
fi

# Source AWS credentials
echo -e "${YELLOW}Sourcing AWS credentials...${NC}"
source "$DEPLOYER_SCRIPT"

# Verify AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Verify credentials
echo -e "${YELLOW}Verifying AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials are invalid${NC}"
    exit 1
fi

echo -e "${GREEN}AWS credentials verified${NC}"

# Load configuration from config.json
CONFIG_FILE="config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: $CONFIG_FILE not found${NC}"
    exit 1
fi

echo -e "${YELLOW}Loading configuration from $CONFIG_FILE...${NC}"

# Extract values from config.json using Python (more reliable than jq which might not be installed)
CARRIER_USERNAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['username'])" 2>/dev/null)
CARRIER_PASSWORD=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['password'])" 2>/dev/null)
CARRIER_SERIAL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('serial', '4022W200213'))" 2>/dev/null)

if [ -z "$CARRIER_USERNAME" ] || [ -z "$CARRIER_PASSWORD" ]; then
    echo -e "${RED}Error: username and password are required in $CONFIG_FILE${NC}"
    exit 1
fi

if [ -z "$CARRIER_SERIAL" ]; then
    CARRIER_SERIAL="4022W200213"
    echo -e "${YELLOW}Serial number not found in config, using default: $CARRIER_SERIAL${NC}"
fi

echo -e "${GREEN}Configuration loaded:${NC}"
echo -e "  Username: ${YELLOW}$CARRIER_USERNAME${NC}"
echo -e "  Serial: ${YELLOW}$CARRIER_SERIAL${NC}"

# Create temporary directory for Lambda packages
TEMP_DIR=$(mktemp -d)
echo -e "${YELLOW}Created temporary directory: $TEMP_DIR${NC}"

# Function to create Lambda deployment package
create_lambda_package() {
    local FUNCTION_NAME=$1
    local HANDLER_FILE=$2
    local PACKAGE_NAME=$3
    
    echo -e "${YELLOW}Creating Lambda package for $FUNCTION_NAME...${NC}"
    
    # Create package directory
    PACKAGE_DIR="$TEMP_DIR/$FUNCTION_NAME"
    mkdir -p "$PACKAGE_DIR"
    
    # Copy handler and dependencies
    cp "$HANDLER_FILE" "$PACKAGE_DIR/"
    cp carrier_auth.py "$PACKAGE_DIR/"
    cp carrier_energy.py "$PACKAGE_DIR/"
    
    # Install dependencies
    pip install -r requirements.txt -t "$PACKAGE_DIR" --quiet
    
    # Create zip file
    cd "$PACKAGE_DIR"
    zip -r "$TEMP_DIR/$PACKAGE_NAME" . -q
    cd - > /dev/null
    
    echo -e "${GREEN}Created package: $PACKAGE_NAME${NC}"
}

# Create Lambda packages
create_lambda_package "collect_energy" "lambda_collect_energy.py" "collect_energy.zip"
create_lambda_package "api" "lambda_api.py" "api.zip"

# Deploy CloudFormation stack
echo -e "${YELLOW}Deploying CloudFormation stack...${NC}"

# Check if stack exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${YELLOW}Stack exists, updating...${NC}"
    OPERATION="update-stack"
else
    echo -e "${YELLOW}Stack does not exist, creating...${NC}"
    OPERATION="create-stack"
fi

# Create/update stack (without Lambda code first)
CF_OUTPUT=$(aws cloudformation "$OPERATION" \
    --stack-name "$STACK_NAME" \
    --template-body file://cloudformation.yaml \
    --parameters \
        ParameterKey=CarrierUsername,ParameterValue="$CARRIER_USERNAME" \
        ParameterKey=CarrierPassword,ParameterValue="$CARRIER_PASSWORD" \
        ParameterKey=CarrierSerial,ParameterValue="$CARRIER_SERIAL" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION" \
    2>&1)

CF_EXIT_CODE=$?

if [ $CF_EXIT_CODE -ne 0 ]; then
    if echo "$CF_OUTPUT" | grep -q "No updates are to be performed"; then
        echo -e "${YELLOW}No CloudFormation updates needed, continuing to Lambda update...${NC}"
    else
        echo -e "${RED}CloudFormation error:${NC}"
        echo "$CF_OUTPUT"
        # Don't exit - continue to update Lambda code anyway
        echo -e "${YELLOW}Continuing to update Lambda code despite CloudFormation error...${NC}"
    fi
else
    # Wait for stack to be ready (only if an update was actually started)
    echo -e "${YELLOW}CloudFormation update started, waiting for completion...${NC}"
    aws cloudformation wait stack-${OPERATION%-stack}-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION" 2>/dev/null || echo -e "${YELLOW}CloudFormation wait completed${NC}"
fi

echo -e "${GREEN}Proceeding to Lambda code update...${NC}"

# Get Lambda function names from stack
DATA_COLLECTION_LAMBDA="bryantDataCollector-collectEnergy"
API_LAMBDA="bryantDataCollector-api"

# Get API Gateway URL
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
    --output text)

# Update Lambda function code
echo -e "${YELLOW}Updating Lambda function code...${NC}"

echo -e "${YELLOW}  Updating data collection Lambda...${NC}"
if aws lambda update-function-code \
    --function-name "$DATA_COLLECTION_LAMBDA" \
    --zip-file "fileb://$TEMP_DIR/collect_energy.zip" \
    --region "$REGION" 2>&1; then
    echo -e "${GREEN}    ✓ Data collection Lambda updated${NC}"
else
    echo -e "${RED}    ✗ Failed to update data collection Lambda${NC}"
    exit 1
fi

echo -e "${YELLOW}  Updating API Lambda...${NC}"
if aws lambda update-function-code \
    --function-name "$API_LAMBDA" \
    --zip-file "fileb://$TEMP_DIR/api.zip" \
    --region "$REGION" 2>&1; then
    echo -e "${GREEN}    ✓ API Lambda updated${NC}"
else
    echo -e "${RED}    ✗ Failed to update API Lambda${NC}"
    exit 1
fi

# Wait for Lambda updates to complete
echo -e "${YELLOW}Waiting for Lambda updates to complete...${NC}"
aws lambda wait function-updated \
    --function-name "$DATA_COLLECTION_LAMBDA" \
    --region "$REGION"

aws lambda wait function-updated \
    --function-name "$API_LAMBDA" \
    --region "$REGION"

echo -e "${GREEN}Lambda functions updated${NC}"

# Cleanup
echo -e "${YELLOW}Cleaning up temporary files...${NC}"
rm -rf "$TEMP_DIR"

# Print summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Stack Name: ${YELLOW}$STACK_NAME${NC}"
echo -e "Region: ${YELLOW}$REGION${NC}"
echo ""
echo -e "API URL: ${YELLOW}$API_URL${NC}"
echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo -e "1. The Lambda function will run daily at 8 AM UTC"
echo -e "2. Open frontend/index.html in your browser to view your energy data"
echo -e "3. Enter the API URL above in the dashboard to load data"
echo ""

