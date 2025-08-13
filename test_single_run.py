#!/usr/bin/env python3
"""
Test script to verify the single execution mode works correctly.
This simulates what happens when GitHub Actions runs the application.
"""

import os
import sys
import subprocess
from pathlib import Path

def test_single_execution():
    """Test the application runs once and exits successfully."""
    print("🧪 Testing single execution mode...")
    
    # Check if .env file exists
    if not Path('.env').exists():
        print("⚠️  Warning: .env file not found. Make sure environment variables are set.")
    
    # Check if route data exists
    if not Path('data/route_data.json').exists():
        print("⚠️  Warning: data/route_data.json not found. Route analysis will be skipped.")
    
    try:
        # Run the application
        print("🚀 Running app.py in single execution mode...")
        result = subprocess.run([
            sys.executable, 'app.py'
        ], capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        if result.returncode == 0:
            print("✅ Application completed successfully!")
            print("\nOutput:")
            print(result.stdout)
            
            if result.stderr:
                print("\nWarnings/Info:")
                print(result.stderr)
                
        else:
            print("❌ Application failed!")
            print(f"Exit code: {result.returncode}")
            print("\nError output:")
            print(result.stderr)
            print("\nStandard output:")
            print(result.stdout)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Application timed out after 5 minutes!")
        return False
    except Exception as e:
        print(f"❌ Error running application: {e}")
        return False

def check_environment():
    """Check if required environment variables are set."""
    print("🔍 Checking environment variables...")
    
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY', 
        'TABLE_NAME',
        'API_KEY',
        'GEOCODE_API_KEY',
        'GROQ_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print("   Make sure these are set in your .env file or environment.")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

def main():
    """Main test function."""
    print("=" * 60)
    print("🧪 TRAFFIC MONITORING - SINGLE EXECUTION TEST")
    print("=" * 60)
    
    # Check environment
    env_ok = check_environment()
    
    # Run single execution test
    test_ok = test_single_execution()
    
    print("\n" + "=" * 60)
    if env_ok and test_ok:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Your application is ready for GitHub Actions deployment!")
    else:
        print("❌ TESTS FAILED!")
        if not env_ok:
            print("   - Fix environment variable issues")
        if not test_ok:
            print("   - Fix application execution issues")
    print("=" * 60)
    
    return 0 if (env_ok and test_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
