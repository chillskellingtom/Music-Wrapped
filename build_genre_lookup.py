#!/usr/bin/env python3
"""
Build Comprehensive Genre Lookup from Apple Music Data

This script creates a comprehensive genre mapping file by combining data from:
- Apple Music Library Tracks.json (most reliable - has Track Identifier + Genre)
- Apple Music - Play History Daily Tracks.csv (Track Identifier + Track Description)
- Apple Music Play Activity.csv (Track Identifier + Song Name)
- Apple Music - Track Play History.csv (Song Name + Artist)

The output is a JSON file that maps:
1. Track Identifier -> Genre (most reliable)
2. Song Name + Artist -> Genre (fallback)
3. Song Name -> Genre (last resort)

Usage:
    python build_genre_lookup.py "/path/to/Apple Music Activity" [output_file.json]
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
import pandas as pd
from typing import Dict, Optional


def normalize_name(name: str) -> str:
    """Normalize a name for better matching."""
    if not name:
        return ''
    normalized = str(name).lower().strip()
    # Remove common punctuation
    for char in ['(', ')', '[', ']', '-', '_', '.', ',', '!', '?', '&', "'", '"']:
        normalized = normalized.replace(char, ' ')
    normalized = ' '.join(normalized.split())
    return normalized


def load_library_tracks(data_dir: Path) -> Dict:
    """Load library tracks and build Track Identifier -> Genre map."""
    library_file = data_dir / "Apple Music Library Tracks.json"
    if not library_file.exists():
        print(f"⚠️  {library_file.name} not found")
        return {}
    
    print(f"📖 Loading {library_file.name}...")
    with open(library_file, 'r', encoding='utf-8') as f:
        tracks = json.load(f)
    
    # Build mappings
    track_id_to_genre = {}
    song_artist_to_genre = {}
    song_to_genre = {}
    song_normalized_to_genre = {}
    
    for track in tracks:
        track_id = track.get('Track Identifier')
        title = track.get('Title', track.get('Name', ''))
        artist = track.get('Artist', track.get('Album Artist', ''))
        genre = track.get('Genre', '')
        
        if not genre or not str(genre).strip():
            continue
        
        genre = str(genre).strip()
        
        # Track Identifier -> Genre (most reliable)
        if track_id:
            try:
                track_id_to_genre[int(track_id)] = genre
            except (ValueError, TypeError):
                pass
        
        # Song Name + Artist -> Genre
        # Key format: song|artist (matching dashboard format)
        if title and artist:
            key = f"{str(title).lower().strip()}|{str(artist).lower().strip()}"
            song_artist_to_genre[key] = genre
            
            # Also normalized version (song|artist format)
            normalized_title = normalize_name(title)
            normalized_artist = normalize_name(artist)
            if normalized_title and normalized_artist:
                normalized_key = f"{normalized_title}|{normalized_artist}"
                song_artist_to_genre[normalized_key] = genre
        
        # Song Name -> Genre (fallback)
        if title:
            song_lower = str(title).lower().strip()
            song_to_genre[song_lower] = genre
            
            # Normalized version
            normalized_title = normalize_name(title)
            if normalized_title:
                song_normalized_to_genre[normalized_title] = genre
    
    print(f"   ✅ Built {len(track_id_to_genre)} Track ID mappings")
    print(f"   ✅ Built {len(song_artist_to_genre)} Song+Artist mappings")
    print(f"   ✅ Built {len(song_to_genre)} Song name mappings")
    
    return {
        'track_id_to_genre': {str(k): v for k, v in track_id_to_genre.items()},
        'song_artist_to_genre': song_artist_to_genre,
        'song_to_genre': song_to_genre,
        'song_normalized_to_genre': song_normalized_to_genre,
    }


def enrich_from_daily_tracks(data_dir: Path, genre_lookup: Dict, library_tracks: list) -> Dict:
    """Enrich genre lookup from daily tracks using Track Identifier to match library_tracks."""
    daily_file = data_dir / "Apple Music - Play History Daily Tracks.csv"
    if not daily_file.exists():
        print(f"⚠️  {daily_file.name} not found")
        return genre_lookup
    
    print(f"📖 Loading {daily_file.name}...")
    try:
        df = pd.read_csv(daily_file, low_memory=False)
        
        # Build Track Identifier -> Genre map from library_tracks if not already done
        track_id_to_genre = {}
        for track in library_tracks:
            track_id = track.get('Track Identifier')
            genre = track.get('Genre', '')
            if track_id and genre and str(genre).strip():
                try:
                    track_id_to_genre[int(track_id)] = str(genre).strip()
                except (ValueError, TypeError):
                    pass
        
        track_id_map = genre_lookup.get('track_id_to_genre', {})
        song_artist_map = genre_lookup.get('song_artist_to_genre', {})
        song_map = genre_lookup.get('song_to_genre', {})
        
        enriched_track_ids = 0
        enriched_song_artist = 0
        
        # Process daily tracks
        if 'Track Identifier' in df.columns:
            for _, row in df.iterrows():
                track_id = row.get('Track Identifier')
                track_desc = row.get('Track Description', '')
                
                # Try to get genre from Track Identifier
                if pd.notna(track_id):
                    try:
                        track_id_int = int(track_id)
                        if track_id_int in track_id_to_genre:
                            genre = track_id_to_genre[track_id_int]
                            # Add to track_id_map if not already there
                            if str(track_id) not in track_id_map:
                                track_id_map[str(track_id)] = genre
                                enriched_track_ids += 1
                            
                            # Also add to song+artist map if we can parse Track Description
                            if pd.notna(track_desc) and ' - ' in str(track_desc):
                                parts = str(track_desc).split(' - ', 1)
                                if len(parts) == 2:
                                    artist = parts[0].strip()
                                    song = parts[1].strip()
                                    # Key format: song|artist (matching dashboard)
                                    key = f"{song.lower().strip()}|{artist.lower().strip()}"
                                    if key not in song_artist_map:
                                        song_artist_map[key] = genre
                                        enriched_song_artist += 1
                                    
                                    # Also add to song map
                                    song_lower = song.lower().strip()
                                    if song_lower not in song_map:
                                        song_map[song_lower] = genre
                    except (ValueError, TypeError):
                        pass
        
        # Update genre_lookup with new mappings
        genre_lookup['track_id_to_genre'] = track_id_map
        genre_lookup['song_artist_to_genre'] = song_artist_map
        genre_lookup['song_to_genre'] = song_map
        
        print(f"   ✅ Enriched {enriched_track_ids} Track ID mappings from daily_tracks")
        print(f"   ✅ Enriched {enriched_song_artist} Song+Artist mappings from daily_tracks")
        print(f"   ✅ Processed {len(df)} daily track records")
    except Exception as e:
        print(f"   ⚠️  Error processing daily tracks: {e}")
        import traceback
        traceback.print_exc()
    
    return genre_lookup


def build_genre_lookup(data_dir: str, output_file: Optional[str] = None) -> str:
    """Build comprehensive genre lookup from all available sources."""
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"❌ Directory not found: {data_dir}")
        sys.exit(1)
    
    print("=" * 60)
    print("🎵 Building Comprehensive Genre Lookup")
    print("=" * 60)
    print()
    
    # Start with library tracks (most reliable)
    genre_lookup = load_library_tracks(data_path)
    
    # Load library tracks for enrichment
    library_file = data_path / "Apple Music Library Tracks.json"
    library_tracks = []
    if library_file.exists():
        with open(library_file, 'r', encoding='utf-8') as f:
            library_tracks = json.load(f)
    
    # Enrich from other sources
    genre_lookup = enrich_from_daily_tracks(data_path, genre_lookup, library_tracks)
    
    # Add metadata
    genre_lookup['metadata'] = {
        'version': '1.0',
        'sources': [
            'Apple Music Library Tracks.json',
            'Apple Music - Play History Daily Tracks.csv',
        ],
        'total_track_id_mappings': len(genre_lookup.get('track_id_to_genre', {})),
        'total_song_artist_mappings': len(genre_lookup.get('song_artist_to_genre', {})),
        'total_song_mappings': len(genre_lookup.get('song_to_genre', {})),
    }
    
    # Save to file
    if output_file is None:
        output_file = data_path / "genre_lookup.json"
    else:
        output_file = Path(output_file)
    
    print()
    print(f"💾 Saving genre lookup to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(genre_lookup, f, indent=2, ensure_ascii=False)
    
    file_size = output_file.stat().st_size / 1024  # KB
    print(f"   ✅ Saved {file_size:.1f} KB")
    print()
    print("=" * 60)
    print("✅ Genre lookup built successfully!")
    print()
    print(f"📊 Summary:")
    print(f"   Track ID mappings: {genre_lookup['metadata']['total_track_id_mappings']:,}")
    print(f"   Song+Artist mappings: {genre_lookup['metadata']['total_song_artist_mappings']:,}")
    print(f"   Song name mappings: {genre_lookup['metadata']['total_song_mappings']:,}")
    print()
    print(f"📤 Next step: Upload to Supabase Storage")
    print(f"   python upload_data_to_supabase.py \"{data_dir}\"")
    print("=" * 60)
    
    return str(output_file)


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_genre_lookup.py <path_to_apple_music_activity> [output_file.json]")
        print("\nExample:")
        print('  python build_genre_lookup.py "/Volumes/dbcooper/Downloads/Apple Media Services information/Apple_Media_Services/Apple Music Activity"')
        sys.exit(1)
    
    data_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    build_genre_lookup(data_dir, output_file)


if __name__ == "__main__":
    main()

