#!/usr/bin/env python3
"""
Upload Apple Music Data to Supabase Storage

This script uploads the Apple Music Activity folder to Supabase Storage
so it can be accessed securely by authenticated users in the dashboard.

Usage:
    python upload_data_to_supabase.py "/path/to/Apple Music Activity"

Requirements:
    - Supabase project with Storage enabled
    - Storage bucket created (see instructions below)
"""

import sys
import os
from pathlib import Path
import zipfile
import tempfile

try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
except ImportError:
    print("❌ Supabase not installed. Run: pip install supabase")
    sys.exit(1)


def create_supabase_client() -> Client:
    """Create Supabase client from environment or secrets."""
    # Try to get from environment variables
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        # Try to read from secrets.toml
        try:
            import streamlit as st
            url = st.secrets.supabase.url
            key = st.secrets.supabase.key
        except:
            print("❌ Supabase credentials not found.")
            print("   Set SUPABASE_URL and SUPABASE_KEY environment variables,")
            print("   or run this from a directory with .streamlit/secrets.toml")
            sys.exit(1)
    
    return create_client(url, key)


def create_storage_bucket(supabase: Client, bucket_name: str = "apple-music-data"):
    """Create a storage bucket if it doesn't exist."""
    try:
        # Try to get bucket
        response = supabase.storage.get_bucket(bucket_name)
        print(f"✅ Bucket '{bucket_name}' already exists")
        return bucket_name
    except Exception:
        # Bucket doesn't exist, create it
        try:
            response = supabase.storage.create_bucket(
                bucket_name,
                options={
                    "public": False,  # Private bucket
                    "file_size_limit": 100 * 1024 * 1024,  # 100MB per file
                }
            )
            print(f"✅ Created bucket '{bucket_name}'")
            return bucket_name
        except Exception as e:
            print(f"❌ Failed to create bucket: {e}")
            print("\n📝 Manual setup:")
            print("   1. Go to Supabase Dashboard → Storage")
            print(f"   2. Create bucket: {bucket_name}")
            print("   3. Set to Private")
            print("   4. Run this script again")
            sys.exit(1)


def upload_file(supabase: Client, bucket: str, file_path: Path, remote_path: str):
    """Upload a single file to Supabase Storage."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Upload file
        response = supabase.storage.from_(bucket).upload(
            remote_path,
            data,
            file_options={"content-type": "application/octet-stream"}
        )
        
        print(f"  ✅ {file_path.name} ({len(data) / 1024:.1f} KB)")
        return True
    except Exception as e:
        print(f"  ❌ {file_path.name}: {e}")
        return False


def upload_data_folder(data_dir: str, bucket_name: str = "apple-music-data"):
    """
    Upload Apple Music Activity folder to Supabase Storage.
    
    Args:
        data_dir: Path to Apple Music Activity folder
        bucket_name: Name of Supabase Storage bucket
    """
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"❌ Directory not found: {data_dir}")
        sys.exit(1)
    
    print(f"📂 Uploading data from: {data_path}")
    print("=" * 60)
    
    # Create Supabase client
    print("\n🔌 Connecting to Supabase...")
    supabase = create_supabase_client()
    
    # Create/verify bucket
    print(f"\n📦 Setting up storage bucket '{bucket_name}'...")
    bucket = create_storage_bucket(supabase, bucket_name)
    
    # Upload files
    print(f"\n📤 Uploading files to bucket '{bucket}'...")
    
    uploaded = 0
    failed = 0
    
    # Upload all CSV and JSON files
    for file_path in data_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in ['.csv', '.json']:
            # Get relative path from data_dir
            rel_path = file_path.relative_to(data_path)
            remote_path = str(rel_path).replace('\\', '/')  # Normalize path
            
            if upload_file(supabase, bucket, file_path, remote_path):
                uploaded += 1
            else:
                failed += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Upload complete!")
    print(f"   Uploaded: {uploaded} files")
    if failed > 0:
        print(f"   Failed: {failed} files")
    
    print(f"\n📝 Next steps:")
    print(f"   1. Set up Row Level Security (RLS) policies in Supabase")
    print(f"   2. The dashboard will automatically load from this bucket")
    print(f"\n🔗 Supabase Storage: https://supabase.com/dashboard/project/{supabase.url.split('//')[1].split('.')[0]}/storage/buckets/{bucket}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python upload_data_to_supabase.py <path_to_apple_music_activity>")
        print("\nExample:")
        print('  python upload_data_to_supabase.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"')
        sys.exit(1)
    
    data_dir = sys.argv[1]
    upload_data_folder(data_dir)


if __name__ == "__main__":
    main()

