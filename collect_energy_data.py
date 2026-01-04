#!/usr/bin/env python3
"""
Carrier Energy Data Collection Script

Collects daily energy data from Carrier Infinity systems and stores it in monthly JSON files.
Runs daily to build a historical database of energy usage.

Usage:
    python collect_energy_data.py

Configuration:
    Requires config.json with username and password, or environment variables:
    - CARRIER_USERNAME
    - CARRIER_PASSWORD
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from carrier_auth import CarrierAuth, load_credentials
from carrier_energy import CarrierEnergy


# Configuration
SERIAL_NUMBER = "4022W200213"  # Update with your system serial number
DATA_DIR = "energy_data"  # Directory to store monthly JSON files


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


def get_monthly_filename(year: int, month: int) -> str:
    """
    Get filename for monthly data file.
    
    Args:
        year: Year (e.g., 2026)
        month: Month (1-12)
        
    Returns:
        Filename like "energy_2026_01.json"
    """
    return f"energy_{year}_{month:02d}.json"


def load_monthly_data(filepath: Path) -> Dict[str, Any]:
    """
    Load existing monthly data from file.
    
    Args:
        filepath: Path to monthly JSON file
        
    Returns:
        Dictionary with monthly data, or empty dict if file doesn't exist
    """
    if not filepath.exists():
        return {}
    
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        return {}
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def save_monthly_data(filepath: Path, data: Dict[str, Any]):
    """
    Save monthly data to file.
    
    Args:
        filepath: Path to monthly JSON file
        data: Data dictionary to save
    """
    # Ensure directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def collect_energy_data(serial: str, data_dir: str = DATA_DIR) -> bool:
    """
    Collect energy data and store in monthly JSON files.
    
    Args:
        serial: System serial number
        data_dir: Directory to store monthly JSON files
        
    Returns:
        True if successful, False otherwise
    """
    # Load credentials
    username, password = load_credentials()
    if not username or not password:
        print("Error: Username and password are required")
        print("Please create a config.json file or set CARRIER_USERNAME and CARRIER_PASSWORD environment variables.")
        return False
    
    # Authenticate
    print("Authenticating...")
    auth = CarrierAuth()
    if not auth.authenticate(username, password):
        print("Error: Authentication failed")
        return False
    
    print("Authentication successful!")
    
    # Get energy data
    print(f"Fetching energy data for serial {serial}...")
    energy_client = CarrierEnergy(auth.get_access_token())
    energy_data = energy_client.get_infinity_energy(serial)
    
    if not energy_data:
        print("Error: Failed to retrieve energy data")
        return False
    
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
        print("Warning: No day1 or day2 data found in response")
        print(f"Available periods: {[p.get('energyPeriodType') for p in periods]}")
        return False
    
    # Get dates for the periods
    today = datetime.now()
    day1_date = get_date_for_period("day1", today)
    day2_date = get_date_for_period("day2", today)
    
    print(f"Found data:")
    if day1_data:
        print(f"  day1 (date: {day1_date})")
    if day2_data:
        print(f"  day2 (date: {day2_date})")
    
    # Store data in monthly files
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    
    # Process day1
    if day1_data:
        day1_dt = datetime.strptime(day1_date, "%Y-%m-%d")
        month_file = data_path / get_monthly_filename(day1_dt.year, day1_dt.month)
        monthly_data = load_monthly_data(month_file)
        
        # Check if data already exists for this date
        if day1_date in monthly_data:
            print(f"  Skipping day1 ({day1_date}) - data already exists")
        else:
            monthly_data[day1_date] = {
                "period_type": "day1",
                "collected_at": today.isoformat(),
                "data": day1_data
            }
            save_monthly_data(month_file, monthly_data)
            print(f"  Saved day1 ({day1_date}) to {month_file.name}")
    
    # Process day2
    if day2_data:
        day2_dt = datetime.strptime(day2_date, "%Y-%m-%d")
        month_file = data_path / get_monthly_filename(day2_dt.year, day2_dt.month)
        monthly_data = load_monthly_data(month_file)
        
        # Check if data already exists for this date
        if day2_date in monthly_data:
            print(f"  Skipping day2 ({day2_date}) - data already exists")
        else:
            monthly_data[day2_date] = {
                "period_type": "day2",
                "collected_at": today.isoformat(),
                "data": day2_data
            }
            save_monthly_data(month_file, monthly_data)
            print(f"  Saved day2 ({day2_date}) to {month_file.name}")
    
    print("Data collection complete!")
    return True


def main():
    """Main entry point"""
    print("=" * 70)
    print("Carrier Energy Data Collection")
    print("=" * 70)
    print()
    
    # You can override the serial number via environment variable
    serial = os.environ.get("CARRIER_SERIAL", SERIAL_NUMBER)
    data_dir = os.environ.get("ENERGY_DATA_DIR", DATA_DIR)
    
    success = collect_energy_data(serial, data_dir)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

