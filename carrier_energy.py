#!/usr/bin/env python3
"""
Carrier Energy Data Query Module

Handles GraphQL queries for Carrier Infinity energy data.
"""

import json
import requests
from typing import Optional, Dict, Any


# GraphQL API endpoint
GRAPHQL_API_BASE = "https://dataservice.infinity.iot.carrier.com"


class CarrierEnergy:
    """Query Carrier Infinity energy data via GraphQL"""
    
    def __init__(self, access_token: str):
        """
        Initialize with an access token.
        
        Args:
            access_token: OAuth 2.0 access token from CarrierAuth
        """
        self.access_token = access_token
        self.session = requests.Session()
    
    def graphql_query(self, query: str, variables: Optional[dict] = None, operation_name: Optional[str] = None) -> Optional[dict]:
        """
        Execute a GraphQL query.
        
        Args:
            query: GraphQL query string
            variables: Optional query variables
            operation_name: Optional operation name
            
        Returns:
            Response data as dict, or None on error
        """
        url = f"{GRAPHQL_API_BASE}/graphql"
        
        data = {"query": query}
        if variables:
            data["variables"] = variables
        if operation_name:
            data["operationName"] = operation_name
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://my.carrier.com",
            "Referer": "https://my.carrier.com/",
            "Mobile-App-Brand": "carrier",
        }
        
        try:
            resp = self.session.post(url, json=data, headers=headers)
            
            if resp.status_code == 200:
                result = resp.json()
                # Check for GraphQL errors
                if result.get("errors"):
                    print(f"GraphQL errors: {result.get('errors')}")
                    return result  # Return anyway so caller can see errors
                return result
            else:
                print(f"API request failed: {resp.status_code}")
                print(f"Response: {resp.text[:500]}")
                return None
        except Exception as e:
            print(f"GraphQL query error: {e}")
            return None
    
    def get_infinity_energy(self, serial: str) -> Optional[Dict[str, Any]]:
        """
        Get infinity energy data for a system.
        
        Args:
            serial: System serial number
            
        Returns:
            Dictionary with energy data, or None on error
        """
        query = """
    query getInfinityEnergy($serial: String!) {
  infinityEnergy(serial: $serial) {
    energyConfig {
      cooling {
        display
        enabled
      }
      eheat {
        display
        enabled
      }
      fan {
        display
        enabled
      }
      fangas {
        display
        enabled
      }
      gas {
        display
        enabled
      }
      hpheat {
        display
        enabled
      }
      looppump {
        display
        enabled
      }
      reheat {
        display
        enabled
      }
      hspf
      seer
    }
    energyPeriods {
      energyPeriodType
      eHeatDollars
      eHeatKwh
      coolingDollars
      coolingKwh
      fanDollars
      fanGasDollars
      fanGasKwh
      fanKwh
      hPHeatDollars
      hPHeatKwh
      loopPumpDollars
      loopPumpKwh
      gasDollars
      gasKwh
      reheatDollars
      reheatKwh
    }
  }
}
    """
        variables = {"serial": serial}
        result = self.graphql_query(query, variables, "getInfinityEnergy")
        
        if result and result.get("data"):
            return result.get("data", {}).get("infinityEnergy")
        
        return None

