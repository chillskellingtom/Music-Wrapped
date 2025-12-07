"""
Apple Music Analytics Dashboard

An interactive Streamlit dashboard for exploring Apple Music listening history.
Built on top of the Music-Wrapped Apple Music parser.

Attribution:
- Apple Music parsing: Music-Wrapped (extended from Spotify-Wrapped by Hossein Mohseni)
  https://github.com/hosseinmh1/Spotify-Wrapped
- Dashboard patterns & visualization inspiration: Audiolytics by gegedobruna
  https://github.com/gegedobruna/Audiolytics
- Extended statistics inspired by: jcblsn/apple-music-wrapped
- Authentication: streamlit-authenticator with bcrypt hashing

Usage:
    streamlit run dashboard.py

    # Or with a specific data directory:
    streamlit run dashboard.py -- --data-dir "/path/to/Apple Music Activity"

Authentication:
    Uses streamlit-authenticator with bcrypt-hashed passwords.
    
    Generate hashed passwords:
        python -c "import streamlit_authenticator as stauth; print(stauth.Hasher(['your-password']).generate())"
    
    Set credentials in .streamlit/secrets.toml:
    
        [auth]
        cookie_name = "music_wrapped_auth"
        cookie_key = "random-32-char-string-here"  # Generate with: openssl rand -hex 16
        cookie_expiry_days = 30
        
        [auth.credentials.usernames.mum]
        name = "Mum"
        password = "$2b$12$..."  # bcrypt hash
        
        [auth.credentials.usernames.dad]
        name = "Dad"  
        password = "$2b$12$..."  # bcrypt hash

Security:
    - Passwords hashed with bcrypt (salted, work factor 12)
    - Timing-attack resistant comparison
    - Secure cookie-based sessions
    - HTTPS required for production (Streamlit Cloud provides this)
"""

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import hashlib
import tempfile
from typing import Optional
import requests
import gzip
import logging

# Set up logging for download operations
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the Apple Music parser from this project
from apple_music_parser import AppleMusicParser

# Import Supabase authentication (industry-standard, SOC2 certified)
from auth_supabase import SupabaseAuth

# Try to import Supabase for storage
try:
    from supabase import create_client
    SUPABASE_STORAGE_AVAILABLE = True
except ImportError:
    SUPABASE_STORAGE_AVAILABLE = False


# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Apple Music Wrapped Dashboard",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better table styling
st.markdown("""
<style>
    .song-table {
        font-size: 14px;
    }
    .album-art {
        width: 40px;
        height: 40px;
        border-radius: 4px;
        object-fit: cover;
    }
    .placeholder-art {
        width: 40px;
        height: 40px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        font-size: 16px;
    }
    div[data-testid="stDataFrame"] {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# CACHING & DATA LOADING
# ============================================================================
@st.cache_data(ttl=3600)  # Cache for 1 hour
def download_data_from_supabase(bucket_name: str = None) -> Optional[str]:
    """
    Download Apple Music data from Supabase Storage to a local temp directory.
    
    Args:
        bucket_name: Name of the Supabase Storage bucket (defaults to "apple-music-data" or from secrets)
    
    Returns:
        Path to local data directory, or None if not available
    """
    if not SUPABASE_STORAGE_AVAILABLE:
        return None
    
    if "supabase" not in st.secrets:
        return None
    
    # Get bucket name from secrets or use default
    if bucket_name is None:
        bucket_name = st.secrets.supabase.get("bucket_name", "apple-music-data")
    
    try:
        # Create Supabase client - use authenticated session token if available
        # This ensures RLS policies work correctly for authenticated users
        if "sb_session" in st.session_state and st.session_state.sb_session:
            # Use authenticated user's access token instead of anon key
            session = st.session_state.sb_session
            access_token = getattr(session, 'access_token', None) or getattr(session, 'accessToken', None)
            if access_token:
                # Create client with user's access token
                supabase = create_client(
                    st.secrets.supabase.url,
                    access_token  # Use access token instead of anon key
                )
            else:
                # Fall back to anon key if no token
                supabase = create_client(
                    st.secrets.supabase.url,
                    st.secrets.supabase.key
                )
        else:
            # Fall back to anon key (may not work with RLS)
            supabase = create_client(
                st.secrets.supabase.url,
                st.secrets.supabase.key
            )
        
        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="apple_music_"))
        temp_dir.mkdir(exist_ok=True)
        
        # Try to list files first (may fail due to RLS)
        files = []
        try:
            # Try listing root directory
            files = supabase.storage.from_(bucket_name).list()
            if files is None:
                files = []
            elif not isinstance(files, list):
                if hasattr(files, 'data'):
                    files = files.data
                elif hasattr(files, '__iter__'):
                    files = list(files)
                else:
                    files = []
        except Exception as e:
            # List might fail due to RLS, but we can still try direct downloads
            pass
        
        # Also try listing with empty path and different path options
        all_files = []
        if files:
            all_files.extend(files)
        
        # Try listing with path parameter (in case files are in subdirectories)
        for path_option in ["", "/", None]:
            try:
                path_files = supabase.storage.from_(bucket_name).list(path=path_option) if path_option is not None else supabase.storage.from_(bucket_name).list()
                if path_files and isinstance(path_files, list) and len(path_files) > 0:
                    all_files.extend(path_files)
            except:
                pass
        
        # Remove duplicates
        seen = set()
        unique_files = []
        for item in all_files:
            name = None
            if isinstance(item, dict):
                name = item.get("name")
            elif isinstance(item, str):
                name = item
            elif hasattr(item, "name"):
                name = item.name
            
            if name and name not in seen:
                seen.add(name)
                unique_files.append(item)
        
        files = unique_files if unique_files else files
        
        # Debug: Log response structure (only in debug mode)
        if logger.level == logging.DEBUG:
            file_names_debug = []
            for item in files:
                if isinstance(item, dict):
                    file_names_debug.append(item.get("name", "unknown"))
                elif isinstance(item, str):
                    file_names_debug.append(item)
                elif hasattr(item, "name"):
                    file_names_debug.append(item.name)
            
            logger.debug(f"Storage list response: {len(files)} files, type: {type(files).__name__}, names: {file_names_debug}")
        
        # Known file names that we expect (in order of importance)
        # Note: Some files may be optional
        expected_files = [
            "Apple Music Play Activity.csv.gz",  # Compressed main file (REQUIRED)
            "Apple Music Play Activity.csv",  # Uncompressed (if uploaded that way)
            "Apple Music - Play History Daily Tracks.csv",  # REQUIRED
            "Apple Music Library Tracks.json",  # REQUIRED (for genres)
            "Apple Music Library Artists.json",  # Optional
            "Apple Music Library Albums.json",  # Optional (for album metadata)
            "Apple Music - Top Content.csv",  # Optional
            "Apple Music - Track Play History.csv",  # Optional (may not exist)
            "Identifier Information.json",  # Optional (may help with matching)
            "genre_lookup.json",  # Comprehensive genre lookup (if generated)
        ]
        
        # If list() returned files, use those; otherwise try expected files
        if files and len(files) > 0:
            # Extract file names from list response
            file_names = []
            for item in files:
                if isinstance(item, dict):
                    name = item.get("name")
                elif isinstance(item, str):
                    name = item
                elif hasattr(item, "name"):
                    name = item.name
                else:
                    continue
                if name:
                    file_names.append(name)
            
            if file_names:
                logger.info(f"Found {len(file_names)} file(s) via list: {', '.join(file_names[:3])}{'...' if len(file_names) > 3 else ''}")
                files_to_download = file_names
            else:
                files_to_download = expected_files
        else:
            # List() returned empty - RLS might block listing but allow direct access
            logger.info("List returned empty (RLS may block listing). Trying direct file access...")
            files_to_download = expected_files
        
        # Download each file
        downloaded = 0
        failed_files = []
        
        with st.spinner("📥 Loading data from secure storage..."):
            total_files = len(files_to_download)
            logger.info(f"Starting download of {total_files} file(s) from Supabase Storage")
            
            for idx, file_path in enumerate(files_to_download):
                logger.info(f"Downloading {file_path}... ({idx + 1}/{total_files})")
                
                try:
                    # Try direct download first
                    try:
                        response = supabase.storage.from_(bucket_name).download(file_path)
                        
                        # Handle different response types
                        if isinstance(response, bytes):
                            data = response
                        elif hasattr(response, 'content'):
                            data = response.content
                        elif hasattr(response, 'read'):
                            data = response.read()
                        else:
                            data = bytes(response) if response else None
                    except Exception as download_error:
                        # If direct download fails, try signed URL
                        error_str = str(download_error)
                        if "404" in error_str or "not found" in error_str.lower():
                            # File doesn't exist, skip it
                            continue
                        
                        # Try signed URL as fallback
                        try:
                            signed_url = supabase.storage.from_(bucket_name).create_signed_url(file_path, 3600)
                            if signed_url and 'signedURL' in signed_url:
                                url = signed_url['signedURL']
                            elif isinstance(signed_url, str):
                                url = signed_url
                            else:
                                raise Exception("Could not create signed URL")
                            
                            # Download from signed URL
                            http_response = requests.get(url, timeout=30)
                            http_response.raise_for_status()
                            data = http_response.content
                        except Exception as signed_error:
                            # Both methods failed
                            raise download_error
                    
                    if not data:
                        raise Exception("No data returned from download")
                    
                    # Determine local filename (remove .gz if compressed)
                    if file_path.endswith('.gz'):
                        local_filename = file_path[:-3]  # Remove .gz
                    else:
                        local_filename = file_path
                    
                    local_path = temp_dir / local_filename
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Decompress if needed
                    if file_path.endswith('.gz'):
                        data = gzip.decompress(data)
                    
                    # Save to temp directory
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    
                    downloaded += 1
                    logger.info(f"✅ Successfully downloaded: {local_filename}")
                except Exception as e:
                    error_str = str(e)
                    # Only track as failed if it's not a 404 (file doesn't exist)
                    # 404s for optional files are OK
                    if "404" not in error_str and "not found" not in error_str.lower():
                        failed_files.append((file_path, error_str))
                        logger.warning(f"⚠️ Failed to download {file_path}: {error_str}")
                    else:
                        logger.debug(f"Skipping optional file {file_path} (not found)")
                    continue
            
            logger.info(f"Download complete: {downloaded} file(s) downloaded, {len(failed_files)} failed")
        
        if downloaded > 0:
            if failed_files:
                logger.warning(f"Downloaded {downloaded} file(s), but {len(failed_files)} failed. Check RLS policies.")
            logger.info(f"Successfully loaded data from Supabase Storage ({downloaded} files)")
            return str(temp_dir)
        else:
            if failed_files:
                error_details = "\n".join([f"  - {name}: {err}" for name, err in failed_files[:3]])
                logger.error(f"Download failed: Could not download any files.\n{error_details}")
                st.error("❌ **Could not load data from storage**. Check logs for details.")
                st.markdown("""
                **Troubleshooting:**
                1. Go to [Supabase Storage](https://supabase.com/dashboard/project/cgmiuzcjowdtaawtdmrg/storage/buckets/apple-music-data)
                2. Verify files are uploaded (check exact file names)
                3. Ensure files are in the root of the bucket (not in subfolders)
                4. Check that file names match exactly (case-sensitive, including spaces)
                """)
            else:
                logger.warning("No files found in Supabase Storage")
            return None
            
    except Exception as e:
        st.warning(f"⚠️ Could not load data from Supabase Storage: {e}")
        return None


@st.cache_resource
def load_parser(data_dir: str, exclude_artists: list = None, 
                exclude_songs: list = None, exclude_genres: list = None) -> AppleMusicParser:
    """Load and cache the Apple Music parser."""
    return AppleMusicParser(
        data_dir,
        exclude_artists=exclude_artists,
        exclude_songs=exclude_songs,
        exclude_genres=exclude_genres
    )


@st.cache_data
def get_play_activity_df(_parser: AppleMusicParser, year: int = None) -> pd.DataFrame:
    """Get the play activity dataframe with preprocessing."""
    if _parser.play_activity is None:
        return pd.DataFrame()
    
    df = _parser.play_activity.copy()
    
    # Parse timestamps
    if 'Event Start Timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df['year'] = df['timestamp'].dt.year
        df['month'] = df['timestamp'].dt.to_period('M').astype(str)
        df['hour'] = df['timestamp'].dt.hour
        df['dow'] = df['timestamp'].dt.day_name()
        df['dow_num'] = df['timestamp'].dt.dayofweek
    
    # Filter by year if specified
    if year and 'year' in df.columns:
        df = df[df['year'] == year]
    
    # Filter for actual plays
    if 'Event Type' in df.columns:
        df = df[df['Event Type'] == 'PLAY_END']
    
    return df


@st.cache_data
def load_genre_lookup(data_dir: str) -> Optional[Dict]:
    """Load comprehensive genre lookup JSON if available."""
    import json
    from pathlib import Path
    
    lookup_file = Path(data_dir) / "genre_lookup.json"
    if not lookup_file.exists():
        return None
    
    try:
        with open(lookup_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load genre_lookup.json: {e}")
        return None


@st.cache_data
def get_full_library_table(_parser: AppleMusicParser, year: int = None) -> pd.DataFrame:
    """
    Build a comprehensive table with song, artist, plays, genre, and album info.
    """
    if _parser.play_activity is None:
        return pd.DataFrame()
    
    df = _parser.play_activity.copy()
    
    # Filter by year if specified
    if year and 'Event Start Timestamp' in df.columns:
        df['Event Start Timestamp'] = pd.to_datetime(df['Event Start Timestamp'], errors='coerce')
        df = df[df['Event Start Timestamp'].dt.year == year]
    
    # Filter for actual plays
    if 'Event Type' in df.columns:
        df = df[df['Event Type'] == 'PLAY_END']
    
    # Get song name column
    if 'Song Name' not in df.columns:
        return pd.DataFrame()
    
    # Clean data
    df = df[df['Song Name'].notna() & (df['Song Name'] != '')]
    
    # Aggregate by song
    agg_dict = {
        'Song Name': 'count',
        'Play Duration Milliseconds': 'sum'
    }
    
    # Include Track Identifier if available (for direct genre matching)
    if 'Track Identifier' in df.columns:
        agg_dict['Track Identifier'] = 'first'  # Take first Track Identifier for each song
    
    # Include album if available
    if 'Album Name' in df.columns:
        agg_dict['Album Name'] = 'first'
    
    # Include artist if available - try multiple column names
    artist_col = None
    available_cols = df.columns.tolist()
    logger.debug(f"Available columns in play_activity: {available_cols}")
    
    for col_name in ['Container Artist Name', 'Artist Name', 'Artist', 'Media Item Artist Name']:
        if col_name in df.columns:
            artist_col = col_name
            agg_dict[col_name] = 'first'
            logger.info(f"Using '{col_name}' column for artist data")
            break
    
    if not artist_col:
        logger.warning("No artist column found in play_activity. Will try to get from other sources.")
    
    song_stats = df.groupby('Song Name').agg(agg_dict).rename(columns={
        'Song Name': 'Plays',
        'Play Duration Milliseconds': 'Total Duration (ms)'
    })
    
    song_stats = song_stats.reset_index()
    
    # Add duration in minutes
    song_stats['Duration (min)'] = (song_stats['Total Duration (ms)'] / 60000).round(1)
    
    # Rename columns for clarity - try multiple artist column names
    if artist_col and artist_col in song_stats.columns:
        song_stats = song_stats.rename(columns={artist_col: 'Artist'})
        # Check if artist data is actually populated (not all empty)
        non_empty = (song_stats['Artist'].astype(str).str.strip() != '').sum()
        if non_empty < len(song_stats) * 0.1:  # Less than 10% populated
            logger.warning(f"Artist column '{artist_col}' from play_activity has mostly empty values ({non_empty}/{len(song_stats)}). Using enriched sources instead.")
            song_stats['Artist'] = 'Unknown'  # Reset to Unknown so fallback works
        else:
            # Fill empty values but keep what we have
            song_stats['Artist'] = song_stats['Artist'].fillna('').astype(str).replace('nan', '').replace('None', '')
    else:
        # Try to get artist from other sources
        song_stats['Artist'] = 'Unknown'
    
    # Always try to enrich from daily_tracks and track_history (even if we got some from play_activity)
    artist_cols_to_try = ['Artist Name', 'Artist', 'Container Artist Name', 'Media Item Artist Name']
    
    # Check if we need to enrich (Artist is Unknown or empty)
    needs_enrichment = (song_stats['Artist'] == 'Unknown') | (song_stats['Artist'].astype(str).str.strip() == '')
    
    if needs_enrichment.any():
        logger.info(f"Enriching {needs_enrichment.sum()}/{len(song_stats)} songs with artist data from enriched sources")
        
        if _parser.daily_tracks is not None and not _parser.daily_tracks.empty:
            # Find which artist column exists
            artist_col = None
            for col in artist_cols_to_try:
                if col in _parser.daily_tracks.columns and 'Song Name' in _parser.daily_tracks.columns:
                    artist_col = col
                    break
            
            if artist_col:
                logger.info(f"Using '{artist_col}' from daily_tracks for artist enrichment")
                # Create mapping, filtering out empty values
                artist_data = _parser.daily_tracks[['Song Name', artist_col]].dropna(subset=[artist_col])
                artist_data = artist_data[artist_data[artist_col].astype(str).str.strip() != '']
                if not artist_data.empty:
                    artist_map = artist_data.set_index('Song Name')[artist_col].to_dict()
                    # Normalize for matching
                    normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in artist_map.items() if pd.notna(v) and str(v).strip() != ''}
                    # Only update songs that need enrichment
                    mask = needs_enrichment
                    song_stats.loc[mask, 'Artist'] = song_stats.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map).fillna(song_stats.loc[mask, 'Artist'])
                    needs_enrichment = (song_stats['Artist'] == 'Unknown') | (song_stats['Artist'].astype(str).str.strip() == '')
        
        if needs_enrichment.any() and _parser.track_history is not None and not _parser.track_history.empty:
            # Also try track history
            artist_col = None
            for col in artist_cols_to_try:
                if col in _parser.track_history.columns and 'Song Name' in _parser.track_history.columns:
                    artist_col = col
                    break
            
            if artist_col:
                logger.info(f"Using '{artist_col}' from track_history for remaining artist data")
                # Create mapping, filtering out empty values
                artist_data = _parser.track_history[['Song Name', artist_col]].dropna(subset=[artist_col])
                artist_data = artist_data[artist_data[artist_col].astype(str).str.strip() != '']
                if not artist_data.empty:
                    artist_map = artist_data.set_index('Song Name')[artist_col].to_dict()
                    # Normalize for matching
                    normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in artist_map.items() if pd.notna(v) and str(v).strip() != ''}
                    # Only update songs that still need enrichment
                    mask = needs_enrichment
                    song_stats.loc[mask, 'Artist'] = song_stats.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map).fillna(song_stats.loc[mask, 'Artist'])
    
    if 'Album Name' in song_stats.columns:
        song_stats = song_stats.rename(columns={'Album Name': 'Album'})
        # Check if album data is actually populated
        non_empty = (song_stats['Album'].astype(str).str.strip() != '').sum()
        if non_empty < len(song_stats) * 0.1:  # Less than 10% populated
            logger.warning(f"Album column from play_activity has mostly empty values ({non_empty}/{len(song_stats)}). Using enriched sources instead.")
            song_stats['Album'] = ''  # Reset to empty so enrichment works
    else:
        song_stats['Album'] = ''
    
    # Enrich album data from daily_tracks if available
    if _parser.daily_tracks is not None and not _parser.daily_tracks.empty:
        if 'Album Name' in _parser.daily_tracks.columns and 'Song Name' in _parser.daily_tracks.columns:
            album_data = _parser.daily_tracks[['Song Name', 'Album Name']].dropna(subset=['Album Name'])
            album_data = album_data[album_data['Album Name'].astype(str).str.strip() != '']
            if not album_data.empty:
                album_map = album_data.set_index('Song Name')['Album Name'].to_dict()
                normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in album_map.items() if pd.notna(v) and str(v).strip() != ''}
                # Only update empty albums
                mask = (song_stats['Album'].astype(str).str.strip() == '')
                song_stats.loc[mask, 'Album'] = song_stats.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map).fillna('')
    
    # Final cleanup: replace any remaining empty/unknown values
    song_stats['Artist'] = song_stats['Artist'].astype(str).replace('nan', 'Unknown').replace('None', 'Unknown').replace('', 'Unknown')
    
    # Ensure all text columns are strings (not categorical)
    for col in ['Song Name', 'Artist', 'Album']:
        if col in song_stats.columns:
            song_stats[col] = song_stats[col].astype(str).replace('nan', '').replace('None', '')
            if col == 'Artist':
                song_stats[col] = song_stats[col].replace('', 'Unknown')  # Keep Unknown for empty artists
    
    # Initialize genre column
    if 'Genre' not in song_stats.columns:
        song_stats['Genre'] = 'Unknown'
    
    # PRIORITY 0: Use comprehensive genre_lookup.json if available (highest priority)
    genre_lookup = None
    # Get data_dir from parser (it's stored as Path object)
    parser_data_dir = getattr(_parser, 'data_dir', None)
    if parser_data_dir:
        genre_lookup = load_genre_lookup(str(parser_data_dir))
    
    if genre_lookup:
        logger.info("Using comprehensive genre_lookup.json for genre matching")
        track_id_map = genre_lookup.get('track_id_to_genre', {})
        song_artist_map = genre_lookup.get('song_artist_to_genre', {})
        song_map = genre_lookup.get('song_to_genre', {})
        song_normalized_map = genre_lookup.get('song_normalized_to_genre', {})
        
        mask = song_stats['Genre'] == 'Unknown'
        if mask.any():
            enriched_count = 0
            
            # Try Track Identifier first
            if 'Track Identifier' in song_stats.columns:
                for idx in song_stats[mask].index:
                    track_id = song_stats.at[idx, 'Track Identifier']
                    if pd.notna(track_id) and str(track_id) in track_id_map:
                        song_stats.at[idx, 'Genre'] = track_id_map[str(track_id)]
                        enriched_count += 1
                        continue
            
            # Try Song Name + Artist
            mask = song_stats['Genre'] == 'Unknown'
            if mask.any():
                for idx in song_stats[mask].index:
                    song_name = str(song_stats.at[idx, 'Song Name']).lower().strip()
                    artist = str(song_stats.at[idx, 'Artist']).lower().strip()
                    if artist and artist != 'unknown':
                        key = f"{song_name}|{artist}"
                        if key in song_artist_map:
                            song_stats.at[idx, 'Genre'] = song_artist_map[key]
                            enriched_count += 1
                            continue
                    
                    # Try normalized
                    normalized_song = ' '.join(song_name.split())
                    normalized_artist = ' '.join(artist.split()) if artist != 'unknown' else ''
                    if normalized_artist:
                        normalized_key = f"{normalized_artist}|{normalized_song}"
                        if normalized_key in song_artist_map:
                            song_stats.at[idx, 'Genre'] = song_artist_map[normalized_key]
                            enriched_count += 1
                            continue
            
            # Try Song Name only
            mask = song_stats['Genre'] == 'Unknown'
            if mask.any():
                for idx in song_stats[mask].index:
                    song_name = str(song_stats.at[idx, 'Song Name']).lower().strip()
                    if song_name in song_map:
                        song_stats.at[idx, 'Genre'] = song_map[song_name]
                        enriched_count += 1
                        continue
                    
                    # Try normalized
                    normalized_song = ' '.join(song_name.split())
                    if normalized_song in song_normalized_map:
                        song_stats.at[idx, 'Genre'] = song_normalized_map[normalized_song]
                        enriched_count += 1
            
            logger.info(f"Enriched {enriched_count} genres using genre_lookup.json")
    
    # PRIORITY 1: Use Track Identifier from play_activity to directly match library_tracks for genre
    # This is the most reliable method since it uses the exact track ID
    if 'Track Identifier' in song_stats.columns and _parser.library_tracks:
        logger.info("Using Track Identifier from play_activity to match genres from library_tracks")
        # Build Track Identifier to Genre map from library_tracks
        track_id_to_genre = {}
        for track in _parser.library_tracks:
            track_id = track.get('Track Identifier')
            genre = track.get('Genre', '')
            if track_id and genre and str(genre).strip():
                try:
                    track_id_to_genre[int(track_id)] = str(genre).strip()
                except (ValueError, TypeError):
                    pass
        
        if track_id_to_genre:
            logger.info(f"Built Track Identifier genre map with {len(track_id_to_genre)} entries")
            # Directly map Track Identifier to Genre
            mask = song_stats['Genre'] == 'Unknown'
            track_ids = song_stats.loc[mask, 'Track Identifier'].dropna()
            if not track_ids.empty:
                enriched_count = 0
                for idx in track_ids.index:
                    track_id = song_stats.at[idx, 'Track Identifier']
                    if pd.notna(track_id):
                        try:
                            track_id_int = int(track_id)
                            if track_id_int in track_id_to_genre:
                                song_stats.at[idx, 'Genre'] = track_id_to_genre[track_id_int]
                                enriched_count += 1
                        except (ValueError, TypeError):
                            pass
                logger.info(f"Enriched {enriched_count} genres using Track Identifier mapping")
    elif _parser.library_tracks:
        # Fallback: Match by Song Name + Artist to library_tracks
        logger.info("Track Identifier not in play_activity. Matching genres by Song Name + Artist to library_tracks")
        # Build Song Name + Artist to Genre map from library_tracks
        song_artist_to_genre = {}
        for track in _parser.library_tracks:
            track_name = track.get('Title', track.get('Name', ''))
            artist = track.get('Artist', track.get('Album Artist', ''))
            genre = track.get('Genre', '')
            if track_name and artist and genre and str(genre).strip():
                # Create normalized key for matching
                key = f"{str(track_name).lower().strip()}|{str(artist).lower().strip()}"
                song_artist_to_genre[key] = str(genre).strip()
        
        if song_artist_to_genre:
            logger.info(f"Built Song+Artist genre map with {len(song_artist_to_genre)} entries")
            # Match by Song Name + Artist
            mask = song_stats['Genre'] == 'Unknown'
            if mask.any():
                enriched_count = 0
                for idx in song_stats[mask].index:
                    song_name = str(song_stats.at[idx, 'Song Name']).lower().strip()
                    artist = str(song_stats.at[idx, 'Artist']).lower().strip()
                    if artist and artist != 'unknown':
                        key = f"{song_name}|{artist}"
                        if key in song_artist_to_genre:
                            song_stats.at[idx, 'Genre'] = song_artist_to_genre[key]
                            enriched_count += 1
                logger.info(f"Enriched {enriched_count} genres using Song+Artist matching to library_tracks")
    
    # PRIORITY 2: Try to get genre from enriched daily_tracks (has Genre from identifier mapping)
    if _parser.daily_tracks is not None and not _parser.daily_tracks.empty:
        if 'Genre' in _parser.daily_tracks.columns and 'Song Name' in _parser.daily_tracks.columns:
            genre_data = _parser.daily_tracks[['Song Name', 'Genre']].dropna(subset=['Genre'])
            genre_data = genre_data[genre_data['Genre'].astype(str).str.strip() != '']
            if not genre_data.empty:
                genre_map = genre_data.set_index('Song Name')['Genre'].to_dict()
                normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in genre_map.items() if pd.notna(v) and str(v).strip() != ''}
                # Only update Unknown genres
                mask = song_stats['Genre'] == 'Unknown'
                song_stats.loc[mask, 'Genre'] = song_stats.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map).fillna('Unknown')
                logger.info(f"Enriched {mask.sum()} genres from daily_tracks")
    
    # Then, try to get genre from library tracks (fallback for remaining Unknown)
    # Create a more robust mapping using both song name and artist
    genre_map_by_name = {}
    genre_map_by_artist_song = {}
    genre_map_normalized = {}  # Normalized (strip, lowercase, no special chars)
    genre_map_normalized_artist_song = {}  # Normalized artist+song
    
    def normalize_name(name):
        """Normalize a name for better matching."""
        if not name:
            return ''
        # Lowercase, strip, remove common punctuation
        normalized = str(name).lower().strip()
        # Remove common punctuation that might differ
        for char in ['(', ')', '[', ']', '-', '_', '.', ',', '!', '?', '&', "'", '"']:
            normalized = normalized.replace(char, ' ')
        # Collapse multiple spaces
        normalized = ' '.join(normalized.split())
        return normalized
    
    if _parser.library_tracks:
        logger.info(f"Loading genres from {len(_parser.library_tracks)} library tracks")
        for track in _parser.library_tracks:
            track_name = track.get('Title', track.get('Name', ''))
            artist = track.get('Artist', track.get('Artist Name', ''))
            genre = track.get('Genre', '')
            
            if track_name and genre:
                # Map by exact song name (lowercase)
                genre_map_by_name[track_name.lower().strip()] = genre
                
                # Map by normalized song name (for fuzzy matching)
                normalized_name = normalize_name(track_name)
                if normalized_name:
                    genre_map_normalized[normalized_name] = genre
                
                # Also map by artist + song for better matching
                if artist:
                    key = f"{artist.lower().strip()}|{track_name.lower().strip()}"
                    genre_map_by_artist_song[key] = genre
                    
                    # Also create normalized version
                    normalized_artist = normalize_name(artist)
                    if normalized_artist and normalized_name:
                        normalized_key = f"{normalized_artist}|{normalized_name}"
                        genre_map_normalized_artist_song[normalized_key] = genre
        
        logger.info(f"Created genre maps: {len(genre_map_by_name)} by name, {len(genre_map_by_artist_song)} by artist+song, {len(genre_map_normalized)} normalized, {len(genre_map_normalized_artist_song)} normalized artist+song")
    else:
        logger.warning("No library_tracks available for genre mapping")
    
    # Try to match genres (only for Unknown genres)
    def get_genre(row):
        # If we already have a genre from daily_tracks, keep it
        current_genre = str(row.get('Genre', 'Unknown')).strip()
        if current_genre and current_genre != 'Unknown':
            return current_genre
        
        song_name = str(row['Song Name']).strip()
        artist = str(row.get('Artist', '')).strip()
        
        # Try exact match (lowercase)
        if song_name.lower() in genre_map_by_name:
            return genre_map_by_name[song_name.lower()]
        
        # Try normalized match (fuzzy)
        normalized_song = normalize_name(song_name)
        if normalized_song and normalized_song in genre_map_normalized:
            return genre_map_normalized[normalized_song]
        
        # Try artist + song match (exact)
        if artist and artist.lower() != 'unknown':
            key = f"{artist.lower()}|{song_name.lower()}"
            if key in genre_map_by_artist_song:
                return genre_map_by_artist_song[key]
            
            # Try normalized artist + song match
            normalized_artist = normalize_name(artist)
            if normalized_artist and normalized_song:
                normalized_key = f"{normalized_artist}|{normalized_song}"
                if normalized_key in genre_map_normalized_artist_song:
                    return genre_map_normalized_artist_song[normalized_key]
        
        return 'Unknown'
    
    # Only update Unknown genres
    mask = song_stats['Genre'] == 'Unknown'
    if mask.any():
        before_count = (~mask).sum()
        song_stats.loc[mask, 'Genre'] = song_stats.loc[mask].apply(get_genre, axis=1)
        after_count = (song_stats['Genre'] != 'Unknown').sum()
        enriched = after_count - before_count
        if enriched > 0:
            logger.info(f"Enriched {enriched} additional genres using name-based matching from library_tracks")
    
    # Log summary
    artists_found = (song_stats['Artist'] != 'Unknown').sum() if 'Artist' in song_stats.columns else 0
    genres_found = (song_stats['Genre'] != 'Unknown').sum() if 'Genre' in song_stats.columns else 0
    logger.info(f"Artist data: {artists_found}/{len(song_stats)} songs have artist info")
    logger.info(f"Genre data: {genres_found}/{len(song_stats)} songs have genre info")
    
    # Debug: Show sample of data
    if logger.level == logging.DEBUG and not song_stats.empty:
        sample = song_stats.head(5)[['Song Name', 'Artist', 'Genre']].to_dict('records')
        logger.debug(f"Sample data: {sample}")
    
    # Clean up: Remove Track Identifier column (internal use only)
    if 'Track Identifier' in song_stats.columns:
        song_stats = song_stats.drop(columns=['Track Identifier'])
    
    # Sort by plays
    song_stats = song_stats.sort_values('Plays', ascending=False)
    
    # Select and order columns
    columns = ['Song Name', 'Artist', 'Album', 'Genre', 'Plays', 'Duration (min)']
    song_stats = song_stats[[c for c in columns if c in song_stats.columns]]
    
    return song_stats


def generate_placeholder_color(text: str) -> str:
    """Generate a consistent color based on text hash."""
    hash_val = int(hashlib.md5(text.encode()).hexdigest()[:6], 16)
    
    # Use a set of nice colors
    colors = [
        '#1DB954',  # Spotify green
        '#E91E63',  # Pink
        '#9C27B0',  # Purple
        '#673AB7',  # Deep purple
        '#3F51B5',  # Indigo
        '#2196F3',  # Blue
        '#00BCD4',  # Cyan
        '#009688',  # Teal
        '#4CAF50',  # Green
        '#FF9800',  # Orange
        '#FF5722',  # Deep orange
        '#795548',  # Brown
    ]
    
    return colors[hash_val % len(colors)]


def get_initials(text: str) -> str:
    """Get initials from text for placeholder."""
    if not text:
        return "?"
    words = text.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return text[0].upper()


# ============================================================================
# VISUALIZATION HELPERS (Patterns from Audiolytics)
# ============================================================================
def render_streaks_calendar(df: pd.DataFrame, threshold_minutes: int = 15, weeks_back: int = 26):
    """
    Render a GitHub-style listening streaks calendar.
    
    Pattern adapted from Audiolytics by gegedobruna.
    https://github.com/gegedobruna/Audiolytics
    """
    if df.empty or 'date' not in df.columns:
        st.info("No data available for streaks calendar.")
        return
    
    # Aggregate daily listening
    df_day = df.groupby('date', as_index=False).agg({
        'Play Duration Milliseconds': 'sum'
    })
    df_day['minutes'] = df_day['Play Duration Milliseconds'].fillna(0) / 60000
    df_day['date'] = pd.to_datetime(df_day['date'])
    df_day = df_day.sort_values('date')
    df_day['meets'] = df_day['minutes'] >= threshold_minutes
    
    # Calculate streaks
    grp = (df_day['meets'] != df_day['meets'].shift()).cumsum()
    df_day['streak_id'] = grp.where(df_day['meets'])
    streak_sizes = df_day.groupby('streak_id', dropna=True).size()
    longest = int(streak_sizes.max()) if not streak_sizes.empty else 0
    
    # Last streak (final streak in the data, not assuming ongoing)
    last_streak = 0
    if not df_day.empty and df_day.iloc[-1]['meets']:
        sid = df_day.iloc[-1]['streak_id']
        last_streak = int((df_day['streak_id'] == sid).sum())
    
    # Display metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric("🏁 Last Streak", f"{last_streak} days")
    with col2:
        st.metric("🏆 Longest Streak", f"{longest} days")
    
    # Build calendar grid
    all_days = pd.DataFrame({
        'date': pd.date_range(df_day['date'].min(), df_day['date'].max(), freq='D')
    })
    all_days = all_days.merge(
        df_day[['date', 'meets', 'minutes']], 
        on='date', 
        how='left'
    ).fillna({'meets': False, 'minutes': 0})
    
    all_days['dow'] = all_days['date'].dt.dayofweek
    all_days['week_start'] = all_days['date'] - pd.to_timedelta(all_days['dow'], unit='D')
    all_days = all_days.sort_values('week_start')
    all_days['week_idx'] = (all_days['week_start'].astype('int64') // 10**9) // (7*24*3600)
    
    # Filter to last N weeks
    max_week = all_days['week_idx'].max()
    keep = all_days[all_days['week_idx'] >= max_week - weeks_back + 1]
    
    # Create heatmap
    heat = alt.Chart(keep).mark_rect(cornerRadius=2).encode(
        x=alt.X('week_idx:O', title='', axis=alt.Axis(labels=False, ticks=False)),
        y=alt.Y('dow:O', title='', sort=[0, 1, 2, 3, 4, 5, 6],
                axis=alt.Axis(labelExpr='["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][datum.value]')),
        color=alt.condition('datum.meets', alt.value('#1DB954'), alt.value('#e0e0e0')),
        tooltip=[
            alt.Tooltip('date:T', title='Date'),
            alt.Tooltip('minutes:Q', title='Minutes', format='.1f'),
            alt.Tooltip('meets:N', title='Met threshold')
        ]
    ).properties(height=160)
    
    st.altair_chart(heat, use_container_width=True)
    st.caption(f"Green = listened ≥{threshold_minutes} min that day. Showing last {weeks_back} weeks.")


def render_hour_day_heatmap(df: pd.DataFrame):
    """
    Render hour × day of week heatmap.
    
    Pattern adapted from Audiolytics by gegedobruna.
    """
    if df.empty or 'hour' not in df.columns or 'dow' not in df.columns:
        st.info("No time data available.")
        return
    
    heat_data = df.groupby(['dow', 'dow_num', 'hour'], as_index=False).agg({
        'Play Duration Milliseconds': 'sum'
    })
    heat_data['minutes'] = heat_data['Play Duration Milliseconds'].fillna(0) / 60000
    
    # Sort days properly
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    chart = alt.Chart(heat_data).mark_rect(cornerRadius=3).encode(
        x=alt.X('hour:O', title='Hour of Day'),
        y=alt.Y('dow:N', title='', sort=day_order),
        color=alt.Color('minutes:Q', 
                       scale=alt.Scale(scheme='greens'),
                       title='Minutes'),
        tooltip=[
            alt.Tooltip('dow:N', title='Day'),
            alt.Tooltip('hour:O', title='Hour'),
            alt.Tooltip('minutes:Q', title='Minutes', format='.1f')
        ]
    ).properties(height=280)
    
    st.altair_chart(chart, use_container_width=True)


def render_daily_minutes_chart(df: pd.DataFrame):
    """Render daily listening minutes line chart."""
    if df.empty or 'date' not in df.columns:
        st.info("No daily data available.")
        return
    
    daily = df.groupby('date', as_index=False).agg({
        'Play Duration Milliseconds': 'sum'
    })
    daily['minutes'] = daily['Play Duration Milliseconds'].fillna(0) / 60000
    daily['date'] = pd.to_datetime(daily['date'])
    
    line = alt.Chart(daily).mark_line(
        point=alt.OverlayMarkDef(filled=True, size=30),
        color='#1DB954'
    ).encode(
        x=alt.X('date:T', title=''),
        y=alt.Y('minutes:Q', title='Minutes'),
        tooltip=[
            alt.Tooltip('date:T', title='Date'),
            alt.Tooltip('minutes:Q', title='Minutes', format='.1f')
        ]
    ).properties(height=300)
    
    st.altair_chart(line, use_container_width=True)


def render_monthly_listening(df: pd.DataFrame):
    """Render monthly listening bar chart."""
    if df.empty or 'month' not in df.columns:
        st.info("No monthly data available.")
        return
    
    monthly = df.groupby('month', as_index=False).agg({
        'Play Duration Milliseconds': 'sum',
        'Song Name': 'count'
    }).rename(columns={'Song Name': 'plays'})
    monthly['hours'] = monthly['Play Duration Milliseconds'].fillna(0) / (1000 * 60 * 60)
    monthly = monthly.sort_values('month')
    
    bars = alt.Chart(monthly).mark_bar(color='#1DB954', cornerRadius=4).encode(
        x=alt.X('month:T', title=''),
        y=alt.Y('hours:Q', title='Hours'),
        tooltip=[
            alt.Tooltip('month:T', title='Month'),
            alt.Tooltip('hours:Q', title='Hours', format='.1f'),
            alt.Tooltip('plays:Q', title='Plays')
        ]
    ).properties(height=300)
    
    st.altair_chart(bars, use_container_width=True)


def render_top_artists_chart(artists_df: pd.DataFrame, limit: int = 15):
    """Render top artists horizontal bar chart."""
    if artists_df.empty:
        st.info("No artist data available.")
        return
    
    top = artists_df.head(limit).copy()
    
    chart = alt.Chart(top).mark_bar(color='#1DB954', cornerRadius=4).encode(
        x=alt.X('play_count:Q', title='Plays'),
        y=alt.Y('artist:N', sort='-x', title=''),
        tooltip=[
            alt.Tooltip('artist:N', title='Artist'),
            alt.Tooltip('play_count:Q', title='Plays'),
            alt.Tooltip('total_duration_hours:Q', title='Hours', format='.1f')
        ]
    ).properties(height=400)
    
    st.altair_chart(chart, use_container_width=True)


def render_top_songs_chart(songs_df: pd.DataFrame, limit: int = 15):
    """Render top songs horizontal bar chart."""
    if songs_df.empty:
        st.info("No song data available.")
        return
    
    top = songs_df.head(limit).copy()
    
    chart = alt.Chart(top).mark_bar(color='#E91E63', cornerRadius=4).encode(
        x=alt.X('play_count:Q', title='Plays'),
        y=alt.Y('Song Name:N', sort='-x', title=''),
        tooltip=[
            alt.Tooltip('Song Name:N', title='Song'),
            alt.Tooltip('play_count:Q', title='Plays'),
            alt.Tooltip('total_duration_hours:Q', title='Hours', format='.2f')
        ]
    ).properties(height=400)
    
    st.altair_chart(chart, use_container_width=True)


def render_genre_breakdown(genres_df: pd.DataFrame):
    """Render genre pie/donut chart."""
    if genres_df.empty:
        st.info("No genre data available.")
        return
    
    top_genres = genres_df.head(8).copy()
    
    chart = alt.Chart(top_genres).mark_arc(innerRadius=50, cornerRadius=4).encode(
        theta=alt.Theta('play_count:Q'),
        color=alt.Color('genre:N', 
                       scale=alt.Scale(scheme='category10'),
                       legend=alt.Legend(title='Genre')),
        tooltip=[
            alt.Tooltip('genre:N', title='Genre'),
            alt.Tooltip('play_count:Q', title='Plays')
        ]
    ).properties(height=350)
    
    st.altair_chart(chart, use_container_width=True)


def render_interactive_library_table(library_df: pd.DataFrame):
    """
    Render an interactive, filterable table with album art placeholders.
    
    Features:
    - Colored album art placeholder based on song/artist
    - Sortable columns
    - Text search/filter
    - Genre filter
    """
    if library_df.empty:
        st.info("No library data available.")
        return
    
    st.markdown("### 🎵 Full Music Library")
    st.markdown("Browse, search, and filter all songs. Click column headers to sort.")
    
    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        search_term = st.text_input(
            "🔍 Search songs, artists, or albums",
            placeholder="Type to search...",
            key="library_search"
        )
    
    with col2:
        # Get unique genres
        genres = ['All Genres'] + sorted(library_df['Genre'].dropna().unique().tolist())
        selected_genre = st.selectbox("🎸 Filter by Genre", genres, key="genre_filter")
    
    with col3:
        min_plays = st.number_input("Min plays", min_value=1, value=1, key="min_plays")
    
    # Apply filters
    filtered_df = library_df.copy()
    
    # Ensure string columns are actually strings (not categorical or mixed types)
    for col in ['Song Name', 'Artist', 'Album', 'Genre']:
        if col in filtered_df.columns:
            filtered_df[col] = filtered_df[col].astype(str).fillna('')
    
    if search_term:
        search_lower = search_term.lower()
        mask = (
            filtered_df['Song Name'].str.lower().str.contains(search_lower, na=False) |
            filtered_df['Artist'].str.lower().str.contains(search_lower, na=False) |
            filtered_df['Album'].str.lower().str.contains(search_lower, na=False)
        )
        filtered_df = filtered_df[mask]
    
    if selected_genre != 'All Genres':
        filtered_df = filtered_df[filtered_df['Genre'] == selected_genre]
    
    filtered_df = filtered_df[filtered_df['Plays'] >= min_plays]
    
    # Show count
    st.markdown(f"**Showing {len(filtered_df):,} songs** (out of {len(library_df):,} total)")
    
    # Add rank column
    filtered_df = filtered_df.reset_index(drop=True)
    filtered_df.index = filtered_df.index + 1
    filtered_df.index.name = '#'
    
    # Create display dataframe with album art placeholder info
    display_df = filtered_df.copy()
    
    # Add color column for reference (won't show in table but useful for custom rendering)
    display_df['_color'] = display_df.apply(
        lambda row: generate_placeholder_color(f"{row['Artist']}-{row['Album']}"), 
        axis=1
    )
    display_df['_initials'] = display_df['Album'].apply(get_initials)
    
    # Configure column display
    column_config = {
        "Song Name": st.column_config.TextColumn(
            "🎵 Song",
            width="large",
        ),
        "Artist": st.column_config.TextColumn(
            "🎤 Artist",
            width="medium",
        ),
        "Album": st.column_config.TextColumn(
            "💿 Album",
            width="medium",
        ),
        "Genre": st.column_config.TextColumn(
            "🎸 Genre",
            width="small",
        ),
        "Plays": st.column_config.NumberColumn(
            "▶️ Plays",
            format="%d",
            width="small",
        ),
        "Duration (min)": st.column_config.NumberColumn(
            "⏱️ Duration",
            format="%.1f min",
            width="small",
        ),
    }
    
    # Hide internal columns
    columns_to_show = ['Song Name', 'Artist', 'Album', 'Genre', 'Plays', 'Duration (min)']
    
    # Display the dataframe with sorting
    st.dataframe(
        display_df[columns_to_show],
        column_config=column_config,
        use_container_width=True,
        height=600,
    )
    
    # Download button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        csv = filtered_df[columns_to_show].to_csv(index=True)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="music_library.csv",
            mime="text/csv"
        )
    
    # Stats for filtered results
    with col3:
        if not filtered_df.empty:
            total_plays = filtered_df['Plays'].sum()
            total_mins = filtered_df['Duration (min)'].sum()
            st.caption(f"📊 {total_plays:,} total plays • {total_mins:,.0f} minutes ({total_mins/60:.1f} hours)")


# ============================================================================
# MAIN DASHBOARD
# ============================================================================
def main():
    # ========================================================================
    # AUTHENTICATION (Supabase - SOC2 certified, forgot password, 2FA)
    # ========================================================================
    auth = SupabaseAuth()
    if not auth.require_auth():
        st.stop()
    
    # Parse command line args for data directory
    parser_args = argparse.ArgumentParser()
    parser_args.add_argument('--data-dir', type=str, default=None)
    
    # Handle Streamlit's argument parsing
    try:
        args, _ = parser_args.parse_known_args()
        default_data_dir = args.data_dir
    except:
        default_data_dir = None
    
    # ========================================================================
    # SIDEBAR
    # ========================================================================
    st.sidebar.title("🎵 Apple Music Dashboard")
    auth.logout_button()  # Add logout button
    st.sidebar.markdown("---")
    
    # Data directory input
    st.sidebar.subheader("📂 Data Source")
    
    # Try to load from Supabase Storage first
    supabase_data_dir = None
    if SUPABASE_STORAGE_AVAILABLE and "supabase" in st.secrets:
        # Show debug info in expander
        with st.sidebar.expander("🔧 Debug: Supabase Config", expanded=False):
            bucket_name = st.secrets.supabase.get("bucket_name", "apple-music-data")
            st.text(f"Bucket: {bucket_name}")
            st.text(f"URL: {st.secrets.supabase.url[:30]}...")
            st.text(f"Key: {'✅ Set' if st.secrets.supabase.key else '❌ Missing'}")
        
        supabase_data_dir = download_data_from_supabase()
        if supabase_data_dir:
            st.sidebar.success("✅ Data loaded from secure storage")
    
    # Check for default path in secrets
    default_path = st.secrets.get("data", {}).get("default_path", "")
    if not default_path:
        default_path = default_data_dir or ""
    
    # Use Supabase data if available, otherwise allow manual input
    if supabase_data_dir:
        data_dir = supabase_data_dir
        st.sidebar.info("📦 Using data from Supabase Storage")
    else:
        data_dir = st.sidebar.text_input(
            "Apple Music Activity folder",
            value=default_path,
            placeholder="/path/to/Apple Music Activity"
        )
    
    if not data_dir:
        st.title("🎵 Apple Music Wrapped Dashboard")
        st.markdown("""
        ### Welcome!
        
        Enter the path to your **Apple Music Activity** folder in the sidebar to get started.
        
        **How to get your data:**
        1. Go to [Apple's Data and Privacy portal](https://privacy.apple.com/)
        2. Sign in and click "Request a copy of your data"
        3. Select "Apple Media Services information"
        4. Download and extract the ZIP file
        5. Find the `Apple Music Activity` folder inside
        
        ---
        
        **Attribution:**
        - Apple Music parsing: [Music-Wrapped](https://github.com/hosseinmh1/Spotify-Wrapped)
        - Dashboard patterns: [Audiolytics](https://github.com/gegedobruna/Audiolytics)
        - Extended stats: [jcblsn/apple-music-wrapped](https://github.com/jcblsn/apple-music-wrapped)
        """)
        return
    
    # Verify data directory exists
    if not Path(data_dir).exists():
        st.error(f"❌ Directory not found: {data_dir}")
        return
    
    # Exclusion filters
    st.sidebar.markdown("---")
    st.sidebar.subheader("🚫 Exclusions")
    
    exclude_artists_input = st.sidebar.text_area(
        "Exclude artists (one per line)",
        placeholder="Artist Name\nAnother Artist",
        height=80
    )
    exclude_artists = [a.strip() for a in exclude_artists_input.split('\n') if a.strip()]
    
    exclude_genres_input = st.sidebar.text_area(
        "Exclude genres (one per line)",
        placeholder="Metal\nExplicit Genre",
        height=60
    )
    exclude_genres = [g.strip() for g in exclude_genres_input.split('\n') if g.strip()]
    
    # Load parser
    with st.spinner("Loading Apple Music data..."):
        try:
            apple_parser = load_parser(
                data_dir,
                exclude_artists=exclude_artists if exclude_artists else None,
                exclude_genres=exclude_genres if exclude_genres else None
            )
        except Exception as e:
            st.error(f"❌ Error loading data: {e}")
            return
    
    # Year filter
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Time Filter")
    
    # Get available years
    df_all = get_play_activity_df(apple_parser)
    if df_all.empty:
        st.error("❌ No play activity data found in this folder.")
        return
    
    available_years = sorted(df_all['year'].dropna().unique().astype(int), reverse=True)
    year_options = ['All Years'] + [str(y) for y in available_years]
    selected_year = st.sidebar.selectbox("Year", year_options)
    
    year_filter = None if selected_year == 'All Years' else int(selected_year)
    
    # ========================================================================
    # MAIN CONTENT
    # ========================================================================
    
    # Get filtered data
    df = get_play_activity_df(apple_parser, year_filter)
    
    # Header
    year_text = str(year_filter) if year_filter else "All Time"
    st.title(f"🎵 Apple Music Wrapped — {year_text}")
    
    if exclude_artists:
        st.caption(f"🚫 Excluding: {', '.join(exclude_artists)}")
    
    st.markdown("---")
    
    # ========================================================================
    # KPIs
    # ========================================================================
    stats = apple_parser.get_play_stats(year_filter)
    diversity = apple_parser.get_diversity_score(year_filter)
    streaks = apple_parser.get_listening_streaks(year_filter)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🎧 Total Plays", f"{stats['total_plays']:,}")
    with col2:
        hours = stats['total_listening_time_hours']
        st.metric("⏱️ Hours Listened", f"{hours:,.1f}")
    with col3:
        st.metric("🎵 Unique Songs", f"{stats['unique_songs']:,}")
    with col4:
        unique_artists = len(apple_parser.get_top_artists(10000, year_filter))
        st.metric("🎤 Unique Artists", f"{unique_artists:,}")
    
    # Secondary KPIs
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        days = stats['total_listening_time_hours'] / 24
        st.metric("📅 Days of Music", f"{days:.1f}")
    with col6:
        st.metric("🔥 Longest Streak", f"{streaks['longest_streak']} days")
    with col7:
        st.metric("🎲 Diversity Score", f"{diversity['diversity_score']:.0f}/100")
    with col8:
        st.metric("🔁 Replay Ratio", f"{diversity['replay_ratio']:.1f}×")
    
    st.markdown("---")
    
    # ========================================================================
    # TABS
    # ========================================================================
    tabs = st.tabs([
        "📈 Overview",
        "🕒 Time Analysis", 
        "🎤 Top Artists",
        "🎵 Top Songs",
        "🎸 Genres",
        "📊 Insights",
        "📋 Full Library"  # NEW TAB
    ])
    
    # ------------------------------------------------------------------------
    # OVERVIEW TAB
    # ------------------------------------------------------------------------
    with tabs[0]:
        st.subheader("📈 Daily Listening")
        st.markdown("Track your listening patterns over time.")
        render_daily_minutes_chart(df)
        
        st.subheader("📅 Monthly Breakdown")
        render_monthly_listening(df)
    
    # ------------------------------------------------------------------------
    # TIME ANALYSIS TAB
    # ------------------------------------------------------------------------
    with tabs[1]:
        st.subheader("🕒 When Do You Listen?")
        st.markdown("Discover your peak listening hours and days.")
        
        render_hour_day_heatmap(df)
        
        st.subheader("🔥 Listening Streaks")
        
        # Calculate actual number of weeks in data
        if not df.empty and 'date' in df.columns:
            df_dates = pd.to_datetime(df['date'], errors='coerce').dropna()
            if not df_dates.empty:
                date_range = (df_dates.max() - df_dates.min()).days
                max_weeks = max(52, (date_range // 7) + 1)  # At least 52, or actual weeks + buffer
            else:
                max_weeks = 52
        else:
            max_weeks = 52
        
        col_thresh, col_weeks = st.columns(2)
        with col_thresh:
            threshold = st.slider("Threshold (min/day)", 5, 60, 15, 5)
        with col_weeks:
            weeks = st.slider("Weeks to show", 8, max_weeks, min(26, max_weeks), 4)
        
        render_streaks_calendar(df, threshold_minutes=threshold, weeks_back=weeks)
        
        # Peak times
        st.subheader("⏰ Peak Listening Times")
        peak = apple_parser.get_peak_listening(year_filter)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if peak['peak_hour'] is not None:
                hour = peak['peak_hour']
                if hour < 6:
                    emoji, desc = "🌙", "Night Owl"
                elif hour < 12:
                    emoji, desc = "☀️", "Morning Person"
                elif hour < 18:
                    emoji, desc = "🌤️", "Afternoon Vibes"
                else:
                    emoji, desc = "🌆", "Evening Grooves"
                st.metric(f"{emoji} Peak Hour", f"{hour:02d}:00", desc)
        with col2:
            if peak['peak_day']:
                st.metric("📅 Peak Day", peak['peak_day'])
        with col3:
            if peak['peak_month']:
                st.metric("📆 Peak Month", peak['peak_month'])
    
    # ------------------------------------------------------------------------
    # TOP ARTISTS TAB
    # ------------------------------------------------------------------------
    with tabs[2]:
        st.subheader("🎤 Your Top Artists")
        
        num_artists = st.slider("Show top N artists", 10, 50, 20, 5, key='artist_slider')
        artists_df = apple_parser.get_top_artists(num_artists, year_filter)
        
        render_top_artists_chart(artists_df, num_artists)
        
        # Data table
        with st.expander("📋 View Full List"):
            st.dataframe(
                artists_df[['artist', 'play_count', 'total_duration_hours']].rename(columns={
                    'artist': 'Artist',
                    'play_count': 'Plays',
                    'total_duration_hours': 'Hours'
                }),
                use_container_width=True,
                hide_index=True
            )
    
    # ------------------------------------------------------------------------
    # TOP SONGS TAB
    # ------------------------------------------------------------------------
    with tabs[3]:
        st.subheader("🎵 Your Top Songs")
        
        num_songs = st.slider("Show top N songs", 10, 50, 20, 5, key='song_slider')
        songs_df = apple_parser.get_top_songs(num_songs, year_filter)
        
        # Enrich with artist data from other sources if missing
        needs_enrichment = (
            'Artist Name' not in songs_df.columns or 
            songs_df['Artist Name'].isna().all() or 
            (songs_df['Artist Name'].astype(str).str.strip() == '').all()
        )
        
        if needs_enrichment:
            logger.info("Artist Name missing in top songs, trying to enrich from other sources")
            
            # Initialize Artist Name column if missing
            if 'Artist Name' not in songs_df.columns:
                songs_df['Artist Name'] = None
            
            # Try to get from track history first (most reliable)
            if apple_parser.track_history is not None and not apple_parser.track_history.empty:
                logger.info(f"track_history columns: {apple_parser.track_history.columns.tolist()}")
                # Try multiple artist column names
                artist_cols = ['Artist Name', 'Artist', 'Container Artist Name']
                for col in artist_cols:
                    if col in apple_parser.track_history.columns and 'Song Name' in apple_parser.track_history.columns:
                        logger.info(f"Using '{col}' from track_history for artist enrichment")
                        artist_map = apple_parser.track_history.set_index('Song Name')[col].dropna().to_dict()
                        # Normalize for matching
                        normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in artist_map.items() if pd.notna(v) and str(v).strip() != ''}
                        mask = songs_df['Artist Name'].isna() | (songs_df['Artist Name'].astype(str).str.strip() == '')
                        if mask.any():
                            mapped_values = songs_df.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map)
                            songs_df.loc[mask, 'Artist Name'] = mapped_values.astype(str)
                        break
            
            # Try daily tracks if still missing
            if (songs_df['Artist Name'].isna().any() or (songs_df['Artist Name'].astype(str).str.strip() == '').any()) and apple_parser.daily_tracks is not None and not apple_parser.daily_tracks.empty:
                artist_cols = ['Artist Name', 'Artist', 'Container Artist Name']
                for col in artist_cols:
                    if col in apple_parser.daily_tracks.columns and 'Song Name' in apple_parser.daily_tracks.columns:
                        logger.info(f"Using '{col}' from daily_tracks for remaining artist data")
                        artist_map = apple_parser.daily_tracks.set_index('Song Name')[col].dropna().to_dict()
                        normalized_map = {str(k).lower().strip(): str(v).strip() for k, v in artist_map.items() if pd.notna(v) and str(v).strip() != ''}
                        mask = songs_df['Artist Name'].isna() | (songs_df['Artist Name'].astype(str).str.strip() == '')
                        if mask.any():
                            mapped_values = songs_df.loc[mask, 'Song Name'].astype(str).str.lower().str.strip().map(normalized_map)
                            songs_df.loc[mask, 'Artist Name'] = mapped_values.astype(str)
                        break
            
            # Fill remaining with Unknown and ensure string type
            songs_df['Artist Name'] = songs_df['Artist Name'].fillna('Unknown').astype(str)
            songs_df['Artist Name'] = songs_df['Artist Name'].replace('', 'Unknown')
            
            logger.info(f"After enrichment: {songs_df['Artist Name'].notna().sum()}/{len(songs_df)} songs have artist info")
        
        render_top_songs_chart(songs_df, num_songs)
        
        # Data table
        with st.expander("📋 View Full List"):
            display_cols = ['Song Name', 'play_count', 'total_duration_hours']
            if 'Album Name' in songs_df.columns:
                display_cols.insert(1, 'Album Name')
            if 'Artist Name' in songs_df.columns:
                display_cols.insert(1, 'Artist Name')
            
            st.dataframe(
                songs_df[[c for c in display_cols if c in songs_df.columns]],
                use_container_width=True,
                hide_index=True
            )
    
    # ------------------------------------------------------------------------
    # GENRES TAB
    # ------------------------------------------------------------------------
    with tabs[4]:
        st.subheader("🎸 Your Top Genres")
        
        genres_df = apple_parser.get_top_genres(10, year_filter)
        
        if not genres_df.empty:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                render_genre_breakdown(genres_df)
            
            with col2:
                st.markdown("### Genre Ranking")
                for i, row in genres_df.iterrows():
                    st.markdown(f"**{i+1}.** {row['genre']}")
        else:
            st.info("No genre data available. Genre information comes from your Apple Music Library.")
    
    # ------------------------------------------------------------------------
    # INSIGHTS TAB
    # ------------------------------------------------------------------------
    with tabs[5]:
        st.subheader("📊 Listening Insights")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🎲 Music Diversity")
            
            score = diversity['diversity_score']
            
            # Progress bar
            st.progress(score / 100)
            st.metric("Diversity Score", f"{score:.0f}/100")
            
            if score >= 70:
                st.success("🌍 You're a musical explorer!")
            elif score >= 40:
                st.info("🎭 You have eclectic taste!")
            else:
                st.warning("💎 You know what you like!")
            
            st.markdown(f"""
            - **Songs per artist:** {diversity['songs_per_artist']:.1f}
            - **Replay ratio:** {diversity['replay_ratio']:.1f}× per song
            - **Top 10 concentration:** {diversity['top_10_concentration']:.1f}% of plays
            """)
        
        with col2:
            st.markdown("### 🔥 Streaks & Activity")
            
            st.metric("Total Listening Days", f"{streaks['total_listening_days']:,}")
            st.metric("Longest Streak", f"{streaks['longest_streak']} days")
            # Handle both 'last_streak' and 'current_streak' for backwards compatibility
            last_streak_value = streaks.get('last_streak', streaks.get('current_streak', 0))
            st.metric("Last Streak", f"{last_streak_value} days")
            
            # Date range
            if stats['date_range']['start']:
                st.markdown(f"""
                ### 📅 Data Range
                **{stats['date_range']['start']}** to **{stats['date_range']['end']}**
                """)
    
    # ------------------------------------------------------------------------
    # FULL LIBRARY TAB (NEW - with interactive table)
    # ------------------------------------------------------------------------
    with tabs[6]:
        # Get full library data
        library_df = get_full_library_table(apple_parser, year_filter)
        render_interactive_library_table(library_df)
    
    # ========================================================================
    # FOOTER
    # ========================================================================
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; font-size: 0.85em;">
    
    **Apple Music Wrapped Dashboard**
    
    Built with ❤️ using:
    • [Music-Wrapped](https://github.com/hosseinmh1/Spotify-Wrapped) (Apple Music parsing)
    • [Audiolytics](https://github.com/gegedobruna/Audiolytics) (dashboard patterns)
    • [jcblsn/apple-music-wrapped](https://github.com/jcblsn/apple-music-wrapped) (extended statistics)
    
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"❌ An error occurred: {e}")
        st.exception(e)
        st.info("Please check the Streamlit Cloud logs for more details.")
