#!/usr/bin/env python3

"""Quick test of the asset workflow"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from demo_session import MockRenderSession

def test_assets():
    print("Testing asset workflow...")
    
    # Create session
    session = MockRenderSession()
    
    print("1. Initial assets (should be empty):")
    assets = session.list_assets()
    print(f"   Assets: {assets}")
    
    print("\n2. Available garments:")
    garments = session.list_garments()
    print(f"   Garments: {garments}")
    
    if garments:
        print(f"\n3. Setting garment: {garments[0]}")
        session.set_garment(garments[0])
        
        print("4. Assets after setting garment:")
        assets = session.list_assets()
        print(f"   Assets: {assets}")
        
        if assets:
            print(f"\n5. Setting asset: {assets[0]}")
            session.set_asset(assets[0])
            print("   Asset set successfully!")
        else:
            print("\n5. No assets available after setting garment!")

if __name__ == "__main__":
    test_assets()