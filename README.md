# Bryant Energy Data Collector

A serverless application that collects daily energy data from Carrier/Bryant HVAC systems and visualizes it in a web dashboard.

## Architecture

- **Lambda Function (Data Collection)**: Runs daily at 8 AM UTC via EventBridge to collect energy data from Carrier API
- **DynamoDB Table**: Stores historical energy data with date as the partition key
- **Lambda Function (API)**: Provides REST API endpoints to query DynamoDB data
- **API Gateway**: Exposes the API Lambda as a RESTful endpoint
- **S3 + Static Website**: Hosts the front-end dashboard with Plotly visualizations

## Prerequisites

- AWS CLI installed and configured (or use the deployer role script)
- Python 3.12+
- pip
- Access to `~/code/bryantDeployerRole.sh` with AWS credentials

## Deployment

1. **Prepare your credentials**:
   - Ensure `~/code/bryantDeployerRole.sh` exists with AWS credentials
   - Or set AWS credentials via environment variables

2. **Run the deployment script**:
   ```bash
   ./deploy.sh
   ```

   The script will:
   - Prompt for Carrier username, password, and serial number
   - Create/update the CloudFormation stack
   - Package and deploy Lambda functions
   - Upload the front-end to S3

3. **Get your URLs**:
   After deployment, the script will output:
   - API Gateway URL (for querying data)
   - Front-end Website URL (for viewing the dashboard)

## Configuration

### Environment Variables (Lambda)

The data collection Lambda uses these environment variables:
- `CARRIER_USERNAME`: Your Carrier/Bryant account email
- `CARRIER_PASSWORD`: Your Carrier/Bryant account password
- `CARRIER_SERIAL`: System serial number (default: 4022W200213)
- `DYNAMODB_TABLE_NAME`: DynamoDB table name (set automatically)

### CloudFormation Parameters

- `CarrierUsername`: Carrier/Bryant username (email)
- `CarrierPassword`: Carrier/Bryant password
- `CarrierSerial`: System serial number

## Usage

### Data Collection

The Lambda function runs automatically daily at 8 AM UTC. It collects:
- `day1`: Yesterday's energy data
- `day2`: Day before yesterday's energy data

Data is stored in DynamoDB with the following structure:
- **Partition Key**: `date` (YYYY-MM-DD format)
- **Attributes**: All energy metrics (kWh and dollars for each component)

### API Endpoints

**GET /data**
- Returns all energy data
- Query parameters:
  - `start_date`: Filter from date (YYYY-MM-DD)
  - `end_date`: Filter to date (YYYY-MM-DD)

Example:
```
GET https://your-api.execute-api.us-east-1.amazonaws.com/prod/data?start_date=2026-01-01&end_date=2026-01-31
```

### Front-end Dashboard

You can use the dashboard in two ways:

**Option 1: Local Use (Recommended for Development)**
1. Deploy the CloudFormation stack to create the API Gateway
2. Get the API Gateway URL from the deployment output
3. Open `frontend/index.html` directly in your browser (double-click or `open frontend/index.html`)
4. Paste the API Gateway URL into the "API URL" field
5. Select a date range and click "Load Data"

**Option 2: S3 Hosting (For Production/Sharing)**
1. The deployment script automatically uploads to S3
2. Open the S3 website URL provided after deployment
3. The API URL is pre-configured
4. Select a date range and click "Load Data"

**Visualizations:**
- Daily Energy Usage (kWh)
- Daily Energy Costs ($)
- Energy Breakdown by Type (stacked area chart)
- Summary statistics (total kWh, total cost, averages)

## Data Structure

Each DynamoDB item contains:
```json
{
  "date": "2026-01-03",
  "serial_number": "4022W200213",
  "period_type": "day1",
  "collected_at": "2026-01-04T14:07:22.665437",
  "eHeatDollars": 0.44,
  "eHeatKwh": 4,
  "coolingDollars": 0,
  "coolingKwh": 0,
  "fanDollars": 0.33,
  "fanGasDollars": 0,
  "fanGasKwh": 0,
  "fanKwh": 3,
  "hPHeatDollars": 2.31,
  "hPHeatKwh": 21,
  "loopPumpDollars": 0,
  "loopPumpKwh": 0,
  "gasDollars": 0,
  "gasKwh": 0,
  "reheatDollars": 0,
  "reheatKwh": 0
}
```

## Local Development

### Running the Collection Script Locally

```bash
# Set environment variables
export CARRIER_USERNAME="your_email@example.com"
export CARRIER_PASSWORD="your_password"
export CARRIER_SERIAL="4022W200213"

# Run the script
python collect_energy_data.py
```

### Testing Lambda Functions Locally

You can test the Lambda functions using the AWS SAM CLI or by creating test events:

```bash
# Test data collection Lambda
aws lambda invoke \
  --function-name bryantDataCollector-collectEnergy \
  --payload '{}' \
  response.json

# Test API Lambda
aws lambda invoke \
  --function-name bryantDataCollector-api \
  --payload '{"httpMethod":"GET","path":"/data"}' \
  response.json
```

## Cost Estimation

- **DynamoDB**: On-demand pricing (~$1.25 per million write units, ~$0.25 per million read units)
- **Lambda**: Free tier includes 1M requests/month, then $0.20 per 1M requests
- **API Gateway**: $3.50 per million API calls
- **S3**: ~$0.023 per GB storage, minimal for static website
- **EventBridge**: Free tier includes 1M custom events/month

For a single system collecting data daily, monthly costs should be under $1.

## Troubleshooting

### Lambda Function Errors

Check CloudWatch Logs:
```bash
aws logs tail /aws/lambda/bryantDataCollector-collectEnergy --follow
aws logs tail /aws/lambda/bryantDataCollector-api --follow
```

### API Gateway Issues

- Verify CORS headers are set correctly
- Check Lambda permissions for API Gateway
- Ensure API Gateway deployment is complete

### Front-end Not Loading Data

- Verify API URL is correct
- Check browser console for CORS errors
- Ensure API Gateway is deployed and accessible

## Cleanup

To delete all resources:

```bash
aws cloudformation delete-stack --stack-name bryantDataCollector --region us-east-1
```

## License

MIT
