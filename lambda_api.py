#!/usr/bin/env python3
"""
API Lambda Function for Querying Energy Data

Provides a REST API endpoint to query energy data from DynamoDB for the front-end.
"""

import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "bryant-energy-data")


def convert_decimals_to_float(obj):
    """
    Recursively convert Decimal types to float for JSON serialization.
    
    Args:
        obj: Object that may contain Decimal values
        
    Returns:
        Object with Decimal values converted to float
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_float(item) for item in obj]
    else:
        return obj


def lambda_handler(event, context):
    """
    Lambda handler for API Gateway requests.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response dictionary
    """
    # Get HTTP method and path
    http_method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    query_params = event.get("queryStringParameters") or {}
    
    # Initialize DynamoDB
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    
    # CORS headers
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    
    # Handle OPTIONS request (CORS preflight)
    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": ""
        }
    
    try:
        if path == "/data" or path == "/data/":
            # Get all data or filtered by date range
            start_date = query_params.get("start_date")
            end_date = query_params.get("end_date")
            
            if start_date and end_date:
                # Query date range
                data = query_date_range(table, start_date, end_date)
            else:
                # Scan all items (for small datasets this is fine)
                data = scan_all_data(table)
            
            # Convert Decimal to float for JSON serialization
            data = convert_decimals_to_float(data)
            
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps(data)
            }
        
        elif path.startswith("/data/"):
            # Get specific date
            date = path.split("/")[-1]
            data = get_date_data(table, date)
            
            if data:
                # Convert Decimal to float for JSON serialization
                data = convert_decimals_to_float(data)
                return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps(data)
                }
            else:
                return {
                    "statusCode": 404,
                    "headers": headers,
                    "body": json.dumps({"error": "Data not found for date"})
                }
        
        else:
            return {
                "statusCode": 404,
                "headers": headers,
                "body": json.dumps({"error": "Not found"})
            }
    
    except Exception as e:
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": str(e)})
        }


def scan_all_data(table) -> List[Dict[str, Any]]:
    """
    Scan all items from DynamoDB table.
    
    Args:
        table: DynamoDB table resource
        
    Returns:
        List of energy data items
    """
    try:
        response = table.scan()
        items = response.get("Items", [])
        
        # Continue scanning if there are more items
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        
        # Sort by date descending
        items.sort(key=lambda x: x.get("date", ""), reverse=True)
        
        return items
    
    except ClientError as e:
        print(f"DynamoDB scan error: {e}")
        raise


def query_date_range(table, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Query items within a date range.
    
    Args:
        table: DynamoDB table resource
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        List of energy data items
    """
    try:
        # Since date is the partition key, we need to scan and filter
        # For a small dataset, this is acceptable
        response = table.scan(
            FilterExpression=Attr("date").between(start_date, end_date)
        )
        items = response.get("Items", [])
        
        # Continue scanning if there are more items
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"],
                FilterExpression=Attr("date").between(start_date, end_date)
            )
            items.extend(response.get("Items", []))
        
        # Sort by date descending
        items.sort(key=lambda x: x.get("date", ""), reverse=True)
        
        return items
    
    except ClientError as e:
        print(f"DynamoDB query error: {e}")
        raise


def get_date_data(table, date: str) -> Optional[Dict[str, Any]]:
    """
    Get data for a specific date.
    
    Args:
        table: DynamoDB table resource
        date: Date string (YYYY-MM-DD)
        
    Returns:
        Energy data item or None
    """
    try:
        response = table.get_item(Key={"date": date})
        return response.get("Item")
    
    except ClientError as e:
        print(f"DynamoDB get_item error: {e}")
        raise

