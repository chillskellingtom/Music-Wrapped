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
    # Try service_role key first (for uploads), fall back to anon key
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        # Try to read from secrets.toml
        try:
            import streamlit as st
            url = st.secrets.supabase.url
            # Try service_role if available, otherwise use anon key
            key = st.secrets.supabase.get("service_key") or st.secrets.supabase.key
        except:
            print("❌ Supabase credentials not found.")
            print("   Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables")
            print("   (Service key is needed for uploads - get it from Supabase Dashboard → Settings → API)")
            sys.exit(1)
    
    return create_client(url, key)


def create_storage_bucket(supabase: Client, bucket_name: str = "apple-music-data"):
    """Create a storage bucket if it doesn't exist."""
    try:
        # Try to list buckets to see if it exists
        buckets = supabase.storage.list_buckets()
        bucket_exists = any(b.name == bucket_name for b in buckets)
        
        if bucket_exists:
            print(f"✅ Bucket '{bucket_name}' already exists")
            return bucket_name
    except Exception as e:
        # If we can't list, try to create anyway
        pass
    
    # Bucket doesn't exist, create it
    try:
        response = supabase.storage.create_bucket(
            bucket_name,
            options={
                "public": False,  # Private bucket
                "file_size_limit": 50 * 1024 * 1024,  # 50MB per file (free tier limit)
            }
        )
        print(f"✅ Created bucket '{bucket_name}'")
        return bucket_name
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
            print(f"✅ Bucket '{bucket_name}' already exists")
            return bucket_name
        elif "413" in error_msg or "too large" in error_msg.lower():
            print(f"⚠️  Bucket creation returned size error (bucket may already exist)")
            print(f"   Attempting to use existing bucket '{bucket_name}'...")
            return bucket_name
        else:
            # Bucket creation failed - might already exist or need manual creation
            # Try to continue anyway (bucket might exist)
            print(f"⚠️  Could not create bucket via API: {e}")
            print(f"   Assuming bucket '{bucket_name}' exists (created manually)")
            print(f"   Continuing with upload...")
            return bucket_name


def compress_file(file_path: Path) -> tuple[bytes, str]:
    """
    Compress a file using gzip if it's large.
    
    Returns:
        (compressed_data, remote_filename)
    """
    import gzip
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    # Always compress files > 10MB (CSV files compress very well)
    if len(data) > 10 * 1024 * 1024:
        compressed = gzip.compress(data, compresslevel=9)
        remote_name = file_path.name + ".gz"
        return compressed, remote_name
    
    return data, file_path.name


def upload_file(supabase: Client, bucket: str, file_path: Path, remote_path: str, compress: bool = True):
    """Upload a single file to Supabase Storage."""
    try:
        # Compress if needed
        if compress:
            data, remote_name = compress_file(file_path)
            remote_path = str(Path(remote_path).parent / remote_name) if "/" in remote_path else remote_name
        else:
            with open(file_path, 'rb') as f:
                data = f.read()
        
        # Check size limit (50MB)
        if len(data) > 50 * 1024 * 1024:
            print(f"  ⚠️  {file_path.name} is {len(data) / 1024 / 1024:.1f} MB (exceeds 50MB limit)")
            print(f"     Skipping - this file is too large for Supabase Storage free tier")
            return False
        
        # Upload file
        content_type = "application/gzip" if remote_path.endswith(".gz") else "application/octet-stream"
        response = supabase.storage.from_(bucket).upload(
            remote_path,
            data,
            file_options={"content-type": content_type}
        )
        
        size_mb = len(data) / 1024 / 1024
        print(f"  ✅ {file_path.name} ({size_mb:.1f} MB)")
        if remote_path.endswith(".gz"):
            print(f"     (compressed)")
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
    print(f"\n📤 Uploading essential files to bucket '{bucket}'...")
    
    # Upload files used by the parser, plus potentially useful ones
    essential_files = [
        "Apple Music Play Activity.csv",  # Main file (may be too large)
        "Apple Music - Play History Daily Tracks.csv",
        "Apple Music - Track Play History.csv",
        "Apple Music Library Tracks.json",  # For genres (REQUIRED)
        "Apple Music Library Artists.json",  # For artist info
        "Apple Music Library Albums.json",  # For album metadata/art (potentially useful)
        "Apple Music - Top Content.csv",  # Top content stats
        "Identifier Information.json",  # May help with matching (potentially useful)
    ]
    
    uploaded = 0
    failed = 0
    skipped = 0
    
    for filename in essential_files:
        file_path = data_path / filename
        
        if not file_path.exists():
            print(f"  ⚠️  {filename} not found, skipping")
            skipped += 1
            continue
        
        # Upload file (will auto-compress if >10MB to fit under 50MB limit)
        if upload_file(supabase, bucket, file_path, filename, compress=True):
            uploaded += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Upload complete!")
    print(f"   Uploaded: {uploaded} files")
    if failed > 0:
        print(f"   Failed: {failed} files")
    if skipped > 0:
        print(f"   Skipped: {skipped} files (not found)")
    print(f"\n💡 Large files (>10MB) were automatically compressed to fit under 50MB limit")
    
    print(f"\n📝 Next steps:")
    print(f"   1. Set up Row Level Security (RLS) policies in Supabase")
    print(f"   2. The dashboard will automatically load from this bucket")
    
    # Extract project ID from URL
    try:
        project_id = url.split('//')[1].split('.')[0] if url else "cgmiuzcjowdtaawtdmrg"
        print(f"\n🔗 Supabase Storage: https://supabase.com/dashboard/project/{project_id}/storage/buckets/{bucket}")
    except:
        print(f"\n🔗 Supabase Storage: https://supabase.com/dashboard/project/cgmiuzcjowdtaawtdmrg/storage/buckets/{bucket}")


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

