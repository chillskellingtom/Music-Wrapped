#!/usr/bin/env python3
"""
Enrich Genre Data Using External APIs

Uses free APIs to look up genre information for songs:
- Last.fm API (free, no auth required)
- Spotify API (optional, requires credentials)

Usage:
    python enrich_genres_api.py "/path/to/Apple Music Activity" [--spotify-client-id CLIENT_ID --spotify-client-secret SECRET]
"""

import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, Optional, Tuple
import argparse


def get_genre_from_lastfm(artist: str, track: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Get genre from Last.fm API.
    
    Args:
        artist: Artist name
        track: Track/song name
        api_key: Optional Last.fm API key (not required for basic queries)
    
    Returns:
        Genre string or None
    """
    if not artist or not track:
        return None
    
    # Last.fm API endpoint
    # Note: For basic queries, you can use a demo API key or no key
    # For production, get a free API key from https://www.last.fm/api
    base_url = "http://ws.audioscrobbler.com/2.0/"
    
    params = {
        'method': 'track.getInfo',
        'api_key': api_key or 'demo',  # Demo key works for limited queries
        'artist': artist,
        'track': track,
        'format': 'json'
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'track' in data and 'toptags' in data['track']:
                tags = data['track']['toptags'].get('tag', [])
                if tags:
                    # Get the top tag (most common genre)
                    genre = tags[0].get('name', '').title()
                    if genre:
                        return genre
        time.sleep(0.25)  # Rate limiting (4 requests/second)
    except Exception as e:
        print(f"   ⚠️  Last.fm API error for {artist} - {track}: {e}")
    
    return None


def get_genre_from_spotify(artist: str, track: str, spotify_client_id: str, spotify_client_secret: str) -> Optional[str]:
    """
    Get genre from Spotify API (requires authentication).
    
    Args:
        artist: Artist name
        track: Track/song name
        spotify_client_id: Spotify API client ID
        spotify_client_secret: Spotify API client secret
    
    Returns:
        Genre string or None
    """
    if not artist or not track:
        return None
    
    try:
        # Get access token
        auth_url = "https://accounts.spotify.com/api/token"
        auth_response = requests.post(
            auth_url,
            data={'grant_type': 'client_credentials'},
            auth=(spotify_client_id, spotify_client_secret),
            timeout=5
        )
        
        if auth_response.status_code != 200:
            return None
        
        access_token = auth_response.json()['access_token']
        headers = {'Authorization': f'Bearer {access_token}'}
        
        # Search for track
        search_url = "https://api.spotify.com/v1/search"
        search_params = {
            'q': f'artist:{artist} track:{track}',
            'type': 'track',
            'limit': 1
        }
        
        search_response = requests.get(search_url, headers=headers, params=search_params, timeout=5)
        if search_response.status_code == 200:
            data = search_response.json()
            tracks = data.get('tracks', {}).get('items', [])
            if tracks:
                # Get artist ID and fetch artist genres
                artist_id = tracks[0]['artists'][0]['id']
                artist_url = f"https://api.spotify.com/v1/artists/{artist_id}"
                artist_response = requests.get(artist_url, headers=headers, timeout=5)
                
                if artist_response.status_code == 200:
                    artist_data = artist_response.json()
                    genres = artist_data.get('genres', [])
                    if genres:
                        return genres[0].title()  # Return first genre
        
        time.sleep(0.1)  # Rate limiting
    except Exception as e:
        print(f"   ⚠️  Spotify API error for {artist} - {track}: {e}")
    
    return None


def enrich_genre_lookup_with_api(
    genre_lookup_file: str,
    output_file: Optional[str] = None,
    lastfm_api_key: Optional[str] = None,
    spotify_client_id: Optional[str] = None,
    spotify_client_secret: Optional[str] = None,
    max_lookups: int = 1000
) -> str:
    """
    Enrich existing genre_lookup.json with data from external APIs.
    
    Args:
        genre_lookup_file: Path to existing genre_lookup.json
        output_file: Output file path (defaults to input file)
        lastfm_api_key: Optional Last.fm API key
        spotify_client_id: Optional Spotify client ID
        spotify_client_secret: Optional Spotify client secret
        max_lookups: Maximum number of API lookups to perform
    
    Returns:
        Path to enriched output file
    """
    lookup_path = Path(genre_lookup_file)
    if not lookup_path.exists():
        print(f"❌ File not found: {genre_lookup_file}")
        sys.exit(1)
    
    print("=" * 60)
    print("🌐 Enriching Genre Lookup with External APIs")
    print("=" * 60)
    print()
    
    # Load existing lookup
    print(f"📖 Loading {lookup_path.name}...")
    with open(lookup_path, 'r', encoding='utf-8') as f:
        genre_lookup = json.load(f)
    
    song_artist_map = genre_lookup.get('song_artist_to_genre', {})
    
    # Find songs without genres
    unknown_keys = []
    for key, genre in song_artist_map.items():
        if not genre or genre == 'Unknown' or genre == '':
            unknown_keys.append(key)
    
    print(f"📊 Found {len(unknown_keys)} songs without genres")
    print(f"   Will look up up to {min(max_lookups, len(unknown_keys))} songs")
    print()
    
    # Enrich with API lookups
    enriched = 0
    failed = 0
    
    for i, key in enumerate(unknown_keys[:max_lookups]):
        if '|' in key:
            song, artist = key.split('|', 1)
        else:
            continue
        
        if i % 100 == 0:
            print(f"   Progress: {i}/{min(max_lookups, len(unknown_keys))} ({enriched} enriched, {failed} failed)")
        
        genre = None
        
        # Try Spotify first (if available)
        if spotify_client_id and spotify_client_secret:
            genre = get_genre_from_spotify(artist, song, spotify_client_id, spotify_client_secret)
        
        # Fall back to Last.fm
        if not genre:
            genre = get_genre_from_lastfm(artist, song, lastfm_api_key)
        
        if genre:
            song_artist_map[key] = genre
            enriched += 1
        else:
            failed += 1
    
    # Update genre_lookup
    genre_lookup['song_artist_to_genre'] = song_artist_map
    genre_lookup['metadata']['api_enriched'] = {
        'enriched_count': enriched,
        'failed_count': failed,
        'total_attempted': min(max_lookups, len(unknown_keys))
    }
    
    # Save enriched lookup
    if output_file is None:
        output_file = str(lookup_path)
    else:
        output_file = str(Path(output_file))
    
    print()
    print(f"💾 Saving enriched genre lookup to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(genre_lookup, f, indent=2, ensure_ascii=False)
    
    print()
    print("=" * 60)
    print("✅ Genre enrichment complete!")
    print(f"   Enriched: {enriched} songs")
    print(f"   Failed: {failed} songs")
    print("=" * 60)
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Enrich genre lookup with external APIs')
    parser.add_argument('genre_lookup_file', help='Path to genre_lookup.json')
    parser.add_argument('--output', '-o', help='Output file path (defaults to input file)')
    parser.add_argument('--lastfm-key', help='Last.fm API key (optional)')
    parser.add_argument('--spotify-client-id', help='Spotify API client ID')
    parser.add_argument('--spotify-client-secret', help='Spotify API client secret')
    parser.add_argument('--max-lookups', type=int, default=1000, help='Maximum API lookups (default: 1000)')
    
    args = parser.parse_args()
    
    enrich_genre_lookup_with_api(
        args.genre_lookup_file,
        args.output,
        args.lastfm_key,
        args.spotify_client_id,
        args.spotify_client_secret,
        args.max_lookups
    )


if __name__ == "__main__":
    main()

