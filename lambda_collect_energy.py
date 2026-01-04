#!/usr/bin/env python3
"""
Carrier Energy Data Collection Lambda Function

Collects daily energy data from Carrier Infinity systems and stores it in DynamoDB.
Triggered daily by EventBridge to build a historical database of energy usage.
"""

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

from carrier_auth import CarrierAuth, load_credentials
from carrier_energy import CarrierEnergy


# Configuration from environment variables
SERIAL_NUMBER = os.environ.get("CARRIER_SERIAL", "4022W200213")
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "bryant-energy-data")


def get_date_for_period(period_type: str, reference_date: Optional[datetime] = None) -> str:
    """
    Convert period type (day1, day2) to ISO date string.
    
    day1 = yesterday (relative to reference_date or today)
    day2 = day before yesterday
    
    Args:
        period_type: Energy period type (day1, day2, etc.)
        reference_date: Reference date (defaults to today)
        
    Returns:
        ISO date string (YYYY-MM-DD)
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    if period_type == "day1":
        # Yesterday
        date = reference_date - timedelta(days=1)
    elif period_type == "day2":
        # Day before yesterday
        date = reference_date - timedelta(days=2)
    else:
        # For other periods (month1, year1, etc.), use reference date
        # These are aggregates, so we'll use the collection date
        date = reference_date
    
    return date.strftime("%Y-%m-%d")


def save_to_dynamodb(table, date: str, period_type: str, data: Dict[str, Any], serial: str) -> bool:
    """
    Save energy data to DynamoDB.
    
    Args:
        table: DynamoDB table resource
        date: Date string (YYYY-MM-DD)
        period_type: Period type (day1, day2, etc.)
        data: Energy data dictionary
        serial: System serial number
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if item already exists
        try:
            response = table.get_item(Key={"date": date})
            if "Item" in response:
                print(f"Data for {date} already exists, skipping")
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
        
        # Helper function to convert float to Decimal
        def to_decimal(value):
            """Convert float/int to Decimal, handling None values"""
            if value is None:
                return Decimal("0")
            return Decimal(str(value))
        
        # Prepare item for DynamoDB (convert all numeric values to Decimal)
        item = {
            "date": date,
            "serial_number": serial,
            "period_type": period_type,
            "collected_at": datetime.now().isoformat(),
            "eHeatDollars": to_decimal(data.get("eHeatDollars", 0)),
            "eHeatKwh": to_decimal(data.get("eHeatKwh", 0)),
            "coolingDollars": to_decimal(data.get("coolingDollars", 0)),
            "coolingKwh": to_decimal(data.get("coolingKwh", 0)),
            "fanDollars": to_decimal(data.get("fanDollars", 0)),
            "fanGasDollars": to_decimal(data.get("fanGasDollars", 0)),
            "fanGasKwh": to_decimal(data.get("fanGasKwh", 0)),
            "fanKwh": to_decimal(data.get("fanKwh", 0)),
            "hPHeatDollars": to_decimal(data.get("hPHeatDollars", 0)),
            "hPHeatKwh": to_decimal(data.get("hPHeatKwh", 0)),
            "loopPumpDollars": to_decimal(data.get("loopPumpDollars", 0)),
            "loopPumpKwh": to_decimal(data.get("loopPumpKwh", 0)),
            "gasDollars": to_decimal(data.get("gasDollars", 0)),
            "gasKwh": to_decimal(data.get("gasKwh", 0)),
            "reheatDollars": to_decimal(data.get("reheatDollars", 0)),
            "reheatKwh": to_decimal(data.get("reheatKwh", 0)),
        }
        
        # Write to DynamoDB
        table.put_item(Item=item)
        print(f"Successfully saved data for {date} ({period_type})")
        return True
        
    except ClientError as e:
        print(f"Error saving to DynamoDB: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


def lambda_handler(event, context):
    """
    Lambda handler function.
    
    Args:
        event: Lambda event (from EventBridge)
        context: Lambda context
        
    Returns:
        Dictionary with statusCode and body
    """
    print("Starting energy data collection...")
    
    # Load credentials from environment variables
    username = os.environ.get("CARRIER_USERNAME")
    password = os.environ.get("CARRIER_PASSWORD")
    
    if not username or not password:
        error_msg = "Error: CARRIER_USERNAME and CARRIER_PASSWORD environment variables are required"
        print(error_msg)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_msg})
        }
    
    # Initialize DynamoDB
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    
    # Authenticate
    print("Authenticating...")
    auth = CarrierAuth()
    if not auth.authenticate(username, password):
        error_msg = "Error: Authentication failed"
        print(error_msg)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_msg})
        }
    
    print("Authentication successful!")
    
    # Get energy data
    print(f"Fetching energy data for serial {SERIAL_NUMBER}...")
    energy_client = CarrierEnergy(auth.get_access_token())
    energy_data = energy_client.get_infinity_energy(SERIAL_NUMBER)
    
    if not energy_data:
        error_msg = "Error: Failed to retrieve energy data"
        print(error_msg)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_msg})
        }
    
    # Extract day1 and day2 periods
    periods = energy_data.get("energyPeriods", [])
    day1_data = None
    day2_data = None
    
    for period in periods:
        period_type = period.get("energyPeriodType")
        if period_type == "day1":
            day1_data = period
        elif period_type == "day2":
            day2_data = period
    
    if not day1_data and not day2_data:
        error_msg = "Warning: No day1 or day2 data found in response"
        print(error_msg)
        print(f"Available periods: {[p.get('energyPeriodType') for p in periods]}")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": error_msg, "warning": True})
        }
    
    # Get dates for the periods
    today = datetime.now()
    day1_date = get_date_for_period("day1", today)
    day2_date = get_date_for_period("day2", today)
    
    print(f"Found data:")
    if day1_data:
        print(f"  day1 (date: {day1_date})")
    if day2_data:
        print(f"  day2 (date: {day2_date})")
    
    # Save data to DynamoDB
    results = []
    
    if day1_data:
        success = save_to_dynamodb(table, day1_date, "day1", day1_data, SERIAL_NUMBER)
        results.append({"date": day1_date, "period": "day1", "success": success})
    
    if day2_data:
        success = save_to_dynamodb(table, day2_date, "day2", day2_data, SERIAL_NUMBER)
        results.append({"date": day2_date, "period": "day2", "success": success})
    
    print("Data collection complete!")
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Data collection complete",
            "results": results
        })
    }

